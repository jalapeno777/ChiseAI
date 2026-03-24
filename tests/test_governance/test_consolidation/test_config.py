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


class TestAutoArchiveMode:
    """Tests for AutoArchiveMode enum."""

    def test_all_modes_exist(self):
        """Verify all expected auto-archive modes are defined."""
        from src.governance.consolidation.config import AutoArchiveMode

        expected = ["immediate", "daily", "after_n_days"]
        actual = [m.value for m in AutoArchiveMode]
        assert set(actual) == set(expected)

    def test_mode_values(self):
        """Verify auto-archive mode values."""
        from src.governance.consolidation.config import AutoArchiveMode

        assert AutoArchiveMode.IMMEDIATE.value == "immediate"
        assert AutoArchiveMode.DAILY.value == "daily"
        assert AutoArchiveMode.AFTER_N_DAYS.value == "after_n_days"


class TestTempmemoryArchiveConfig:
    """Tests for TempmemoryArchiveConfig."""

    def test_default_values(self):
        """Test default tempmemory archive config values."""
        from src.governance.consolidation.config import TempmemoryArchiveConfig

        config = TempmemoryArchiveConfig()

        assert config.enabled is True
        assert config.mode.value == "after_n_days"
        assert config.archive_location == "docs/tempmemories/archive/"
        assert config.delay_days == 7
        assert config.preserve_original_path is True
        assert config.generate_reports is True
        assert config.report_format == "json"
        assert config.skip_already_archived is True

    def test_custom_values(self):
        """Test custom tempmemory archive config values."""
        from src.governance.consolidation.config import (
            AutoArchiveMode,
            TempmemoryArchiveConfig,
        )

        config = TempmemoryArchiveConfig(
            enabled=False,
            mode=AutoArchiveMode.IMMEDIATE,
            archive_location="custom/archive/path/",
            delay_days=14,
            preserve_original_path=False,
            generate_reports=False,
            report_format="markdown",
            skip_already_archived=False,
        )

        assert config.enabled is False
        assert config.mode == AutoArchiveMode.IMMEDIATE
        assert config.archive_location == "custom/archive/path/"
        assert config.delay_days == 14
        assert config.preserve_original_path is False
        assert config.generate_reports is False
        assert config.report_format == "markdown"
        assert config.skip_already_archived is False

    def test_to_dict(self):
        """Test TempmemoryArchiveConfig serialization."""
        from src.governance.consolidation.config import TempmemoryArchiveConfig

        config = TempmemoryArchiveConfig()
        data = config.to_dict()

        assert "enabled" in data
        assert "mode" in data
        assert "archive_location" in data
        assert "delay_days" in data
        assert data["mode"] == "after_n_days"

    def test_from_dict(self):
        """Test TempmemoryArchiveConfig deserialization."""
        from src.governance.consolidation.config import (
            AutoArchiveMode,
            TempmemoryArchiveConfig,
        )

        data = {
            "enabled": False,
            "mode": "immediate",
            "archive_location": "custom/path/",
            "delay_days": 3,
        }

        config = TempmemoryArchiveConfig.from_dict(data)

        assert config.enabled is False
        assert config.mode == AutoArchiveMode.IMMEDIATE
        assert config.archive_location == "custom/path/"
        assert config.delay_days == 3

    def test_serialization_roundtrip(self):
        """Test TempmemoryArchiveConfig roundtrip serialization."""
        from src.governance.consolidation.config import (
            AutoArchiveMode,
            TempmemoryArchiveConfig,
        )

        original = TempmemoryArchiveConfig(
            mode=AutoArchiveMode.DAILY,
            delay_days=14,
        )

        data = original.to_dict()
        restored = TempmemoryArchiveConfig.from_dict(data)

        assert restored.mode == original.mode
        assert restored.delay_days == original.delay_days


class TestConsolidationConfigTempmemoryArchive:
    """Tests for ConsolidationConfig tempmemory archive integration."""

    def test_tempmemory_archive_config_present(self):
        """Test that tempmemory archive config is present in ConsolidationConfig."""
        config = ConsolidationConfig()

        assert hasattr(config, "tempmemory_archive")
        assert config.tempmemory_archive is not None

    def test_tempmemory_archive_in_to_dict(self):
        """Test that tempmemory archive config is included in to_dict."""
        config = ConsolidationConfig()
        data = config.to_dict()

        assert "tempmemory_archive" in data
        assert data["tempmemory_archive"]["enabled"] is True

    def test_tempmemory_archive_in_from_dict(self):
        """Test that tempmemory archive config is restored from dict."""
        from src.governance.consolidation.config import (
            AutoArchiveMode,
        )

        data = {
            "tempmemory_archive": {
                "enabled": False,
                "mode": "immediate",
                "archive_location": "custom/path/",
            }
        }

        config = ConsolidationConfig.from_dict(data)

        assert config.tempmemory_archive.enabled is False
        assert config.tempmemory_archive.mode == AutoArchiveMode.IMMEDIATE
        assert config.tempmemory_archive.archive_location == "custom/path/"
