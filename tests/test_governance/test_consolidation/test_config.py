"""
Tests for Memory Consolidation Configuration.

Story: ST-GOV-005
"""

from datetime import time

from src.governance.consolidation.config import (
    ConsolidationConfig,
    MemoryPriority,
    MemoryType,
    RetentionPolicy,
)


class TestMemoryType:
    """Tests for MemoryType enum."""

    def test_all_memory_types_exist(self):
        """Verify all expected memory types are defined."""
        expected = [
            "decision",
            "pattern",
            "anti-pattern",
            "summary",
            "learning",
            "incident",
            "context",
        ]
        actual = [t.value for t in MemoryType]
        assert set(actual) == set(expected)

    def test_memory_type_values_are_lowercase(self):
        """Verify memory type values use kebab-case convention."""
        for mt in MemoryType:
            assert mt.value == mt.value.lower()
            assert " " not in mt.value


class TestMemoryPriority:
    """Tests for MemoryPriority enum."""

    def test_priority_ordering(self):
        """Verify priority levels are properly ordered."""
        assert MemoryPriority.LOW.value < MemoryPriority.MEDIUM.value
        assert MemoryPriority.MEDIUM.value < MemoryPriority.HIGH.value
        assert MemoryPriority.HIGH.value < MemoryPriority.GOLDEN.value

    def test_golden_is_highest(self):
        """Verify GOLDEN is the highest priority."""
        assert MemoryPriority.GOLDEN.value == 4


class TestRetentionPolicy:
    """Tests for RetentionPolicy dataclass."""

    def test_default_values(self):
        """Test default retention policy values."""
        policy = RetentionPolicy(memory_type=MemoryType.DECISION)

        assert policy.memory_type == MemoryType.DECISION
        assert policy.retention_days == 90
        assert policy.archive_to_cold is True
        assert policy.min_access_count == 0
        assert policy.preserve_if_tagged == []

    def test_custom_values(self):
        """Test custom retention policy values."""
        policy = RetentionPolicy(
            memory_type=MemoryType.INCIDENT,
            retention_days=365,
            archive_to_cold=True,
            min_access_count=2,
            preserve_if_tagged=["postmortem", "critical"],
        )

        assert policy.retention_days == 365
        assert policy.min_access_count == 2
        assert "postmortem" in policy.preserve_if_tagged


class TestConsolidationConfig:
    """Tests for ConsolidationConfig."""

    def test_default_schedule_time(self):
        """Test default schedule is 2 AM UTC."""
        config = ConsolidationConfig()

        assert config.schedule_time.hour == 2
        assert config.schedule_time.minute == 0

    def test_default_disabled(self):
        """Test consolidation is disabled by default."""
        config = ConsolidationConfig()

        assert config.enabled is False

    def test_default_dry_run(self):
        """Test dry run is enabled by default."""
        config = ConsolidationConfig()

        assert config.dry_run is True

    def test_rollback_retention_default(self):
        """Test default rollback retention is 7 days."""
        config = ConsolidationConfig()

        assert config.rollback_retention_days == 7

    def test_all_memory_types_have_policies(self):
        """Test all memory types have default retention policies."""
        config = ConsolidationConfig()

        for mt in MemoryType:
            policy = config.get_policy(mt)
            assert policy is not None
            assert policy.memory_type == mt

    def test_get_policy_returns_default_for_unknown(self):
        """Test get_policy returns a default policy for unknown types."""
        config = ConsolidationConfig()

        # This should still work and return a policy
        policy = config.get_policy(MemoryType.DECISION)
        assert policy.retention_days == 90  # Default for DECISION

    def test_incident_policy_has_preserve_tags(self):
        """Test incident policy includes preservation tags."""
        config = ConsolidationConfig()

        policy = config.get_policy(MemoryType.INCIDENT)
        assert "postmortem" in policy.preserve_if_tagged
        assert "critical" in policy.preserve_if_tagged

    def test_golden_promotion_thresholds(self):
        """Test golden promotion thresholds are set."""
        config = ConsolidationConfig()

        assert config.golden_min_access_count == 5
        assert config.golden_min_age_days == 30
        assert config.golden_min_relevance_score == 0.85

    def test_to_dict(self):
        """Test config serialization to dict."""
        config = ConsolidationConfig()
        data = config.to_dict()

        assert "schedule_time" in data
        assert "enabled" in data
        assert "dry_run" in data
        assert "rollback_retention_days" in data
        assert data["schedule_time"] == "02:00:00"

    def test_from_dict(self):
        """Test config deserialization from dict."""
        data = {
            "schedule_time": "03:30:00",
            "enabled": True,
            "dry_run": False,
            "rollback_retention_days": 14,
            "golden_min_access_count": 10,
        }

        config = ConsolidationConfig.from_dict(data)

        assert config.schedule_time == time(3, 30)
        assert config.enabled is True
        assert config.dry_run is False
        assert config.rollback_retention_days == 14
        assert config.golden_min_access_count == 10

    def test_serialization_roundtrip(self):
        """Test config can be serialized and deserialized."""
        original = ConsolidationConfig(
            enabled=True,
            dry_run=False,
            rollback_retention_days=14,
        )

        data = original.to_dict()
        restored = ConsolidationConfig.from_dict(data)

        assert restored.enabled == original.enabled
        assert restored.dry_run == original.dry_run
        assert restored.rollback_retention_days == original.rollback_retention_days

    def test_feature_flag_key(self):
        """Test feature flag key is set correctly."""
        config = ConsolidationConfig()

        assert config.feature_flag_key == (
            "chise:feature_flags:governance:consolidation_enabled"
        )

    def test_cold_storage_path(self):
        """Test cold storage path is configured."""
        config = ConsolidationConfig()

        assert config.cold_storage_path == "/data/chiseai/cold_storage/memories"

    def test_golden_collection_name(self):
        """Test golden collection name is configured."""
        config = ConsolidationConfig()

        assert config.golden_collection == "ChiseAI_golden"

    def test_batch_size_default(self):
        """Test default batch size."""
        config = ConsolidationConfig()

        assert config.batch_size == 100

    def test_max_concurrent_operations(self):
        """Test max concurrent operations setting."""
        config = ConsolidationConfig()

        assert config.max_concurrent_operations == 10
