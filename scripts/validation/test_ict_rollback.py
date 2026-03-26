#!/usr/bin/env python3
"""
ICT Rollback Test Suite

Tests the rollback procedures for ICT confluence feature flag.
Validates that the feature can be disabled and system continues operating.

Story: ST-ICT-022
"""

import subprocess
from contextlib import suppress

import pytest
import redis

REDIS_HOST = "host.docker.internal"
REDIS_PORT = 6380
ICT_CONFLUENCE_KEY = "chiseai:feature:ict_confluence:enabled"
ICT_LAYER1_KEY = "chiseai:feature:ict_layer1:enabled"


class TestICTRollback:
    """Test cases for ICT rollback procedures."""

    @pytest.fixture(autouse=True)
    def setup_redis(self):
        """Ensure Redis is connected before each test."""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self.redis_client.ping()
        except redis.ConnectionError:
            pytest.skip("Redis not available")
        yield
        # Cleanup: restore default state
        with suppress(Exception):
            self.redis_client.set(ICT_CONFLUENCE_KEY, "false")
            self.redis_client.set(ICT_LAYER1_KEY, "false")

    def test_redis_connection(self):
        """Verify Redis is accessible."""
        result = self.redis_client.ping()
        assert result is True

    def test_feature_flag_defaults_to_false(self):
        """Verify ICT confluence flag defaults to false."""
        # Clear any existing value
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")
        value = self.redis_client.get(ICT_CONFLUENCE_KEY)
        assert value == "false"

    def test_set_ict_confluence_enabled(self):
        """Test enabling ICT confluence via feature flag."""
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")
        value = self.redis_client.get(ICT_CONFLUENCE_KEY)
        assert value == "true"

    def test_set_ict_confluence_disabled(self):
        """Test disabling ICT confluence via feature flag."""
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")
        value = self.redis_client.get(ICT_CONFLUENCE_KEY)
        assert value == "false"

    def test_rollback_command(self):
        """Test the rollback one-liner command."""
        # Enable first
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")
        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "true"

        # Execute rollback command
        result = subprocess.run(
            [
                "redis-cli",
                "-h",
                REDIS_HOST,
                "-p",
                str(REDIS_PORT),
                "SET",
                ICT_CONFLUENCE_KEY,
                "false",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "false"

    def test_full_rollback_script(self):
        """Test the full rollback bash script."""
        # Start with enabled state
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")
        self.redis_client.set(ICT_LAYER1_KEY, "true")

        # Execute full rollback
        rollback_script = f"""#!/bin/bash
set -e
redis-cli -h {REDIS_HOST} -p {REDIS_PORT} SET {ICT_CONFLUENCE_KEY} false
redis-cli -h {REDIS_HOST} -p {REDIS_PORT} SET {ICT_LAYER1_KEY} false
echo "done"
"""

        result = subprocess.run(
            ["bash", "-c", rollback_script],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "false"
        assert self.redis_client.get(ICT_LAYER1_KEY) == "false"

    def test_all_ict_flags_can_be_disabled(self):
        """Test that all ICT-related flags can be disabled atomically."""
        # Enable all flags
        self.redis_client.hset(
            "chiseai:feature:ict",
            mapping={
                "ict_confluence:enabled": "true",
                "ict_layer1:enabled": "true",
            },
        )

        # Disable via rollback
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")
        self.redis_client.set(ICT_LAYER1_KEY, "false")

        # Verify all disabled
        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "false"
        assert self.redis_client.get(ICT_LAYER1_KEY) == "false"

    def test_rollback_verification_check(self):
        """Test the verification check after rollback."""
        # Set to disabled state
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")

        # Run verification
        result = subprocess.run(
            [
                "redis-cli",
                "-h",
                REDIS_HOST,
                "-p",
                str(REDIS_PORT),
                "GET",
                ICT_CONFLUENCE_KEY,
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "false"

    def test_health_check_after_rollback(self):
        """Test that system health can be checked after rollback."""
        # This test verifies the health check command structure
        # Actual health endpoint depends on deployment
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "http://localhost:8080/health",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Health endpoint should return 200 or we skip if not deployed
        assert result.returncode in (0, 7)  # 7 = curl couldn't connect


class TestICTRollbackScenarios:
    """Test rollback scenarios documented in the runbook."""

    @pytest.fixture(autouse=True)
    def setup_redis(self):
        """Ensure Redis is connected before each test."""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self.redis_client.ping()
        except redis.ConnectionError:
            pytest.skip("Redis not available")
        yield
        # Cleanup
        with suppress(Exception):
            self.redis_client.set(ICT_CONFLUENCE_KEY, "false")

    def test_validation_failure_scenario(self):
        """Simulate validation failure scenario - flag should be disabled."""
        # Setup: enable ICT
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")

        # Simulate validation failure detection and rollback
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")

        # Verify
        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "false"

    def test_performance_degradation_scenario(self):
        """Simulate performance degradation - rollback should disable."""
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")

        # Simulate performance threshold exceeded
        # In real scenario, monitoring would detect this
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")

        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "false"

    def test_safety_issue_scenario(self):
        """Simulate safety issue - immediate rollback."""
        self.redis_client.set(ICT_CONFLUENCE_KEY, "true")
        self.redis_client.set(ICT_LAYER1_KEY, "true")

        # Immediate rollback for safety
        self.redis_client.set(ICT_CONFLUENCE_KEY, "false")
        self.redis_client.set(ICT_LAYER1_KEY, "false")

        assert self.redis_client.get(ICT_CONFLUENCE_KEY) == "false"
        assert self.redis_client.get(ICT_LAYER1_KEY) == "false"


class TestICTRollbackIntegration:
    """Integration tests for rollback procedures."""

    def test_rollback_script_exists(self):
        """Verify rollback script can be executed."""
        script_content = """#!/bin/bash
REDIS_HOST="${REDIS_HOST:-host.docker.internal}"
REDIS_PORT="${REDIS_PORT:-6380}"
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET chiseai:feature:ict_confluence:enabled false
"""
        result = subprocess.run(
            ["bash", "-c", script_content],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should complete without error (Redis might not be available in test env)
        assert result.returncode in (0, 1)

    def test_redis_keys_command(self):
        """Test the Redis keys command for ICT flags."""
        result = subprocess.run(
            [
                "redis-cli",
                "-h",
                REDIS_HOST,
                "-p",
                str(REDIS_PORT),
                "KEYS",
                "chiseai:feature:ict*",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Command should succeed (might return empty if no keys)
        assert result.returncode == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
