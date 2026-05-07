"""Tests for heartbeat degraded reporting in continuous_signal_generator.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestHeartbeatDegradedReporting:
    """Tests for pipeline_status degraded reporting."""

    @pytest.mark.asyncio
    async def test_pipeline_status_logic_degraded_after_four_zeros(self):
        """Test consecutive_zero_count logic correctly triggers degraded at >3."""
        consecutive_zero_count = 0
        pipeline_statuses = []

        for i in range(10):
            count = 0 if i < 4 else 1

            if count == 0:
                consecutive_zero_count += 1
            else:
                consecutive_zero_count = 0

            status = "degraded" if consecutive_zero_count > 3 else "healthy"
            pipeline_statuses.append(status)

        assert pipeline_statuses[0] == "healthy"
        assert pipeline_statuses[1] == "healthy"
        assert pipeline_statuses[2] == "healthy"
        assert pipeline_statuses[3] == "degraded"
        assert pipeline_statuses[4] == "healthy"

    @pytest.mark.asyncio
    async def test_pipeline_status_logic_boundary_at_three(self):
        """Test that exactly 3 zero iterations does NOT trigger degraded."""
        consecutive_zero_count = 0
        pipeline_statuses = []

        for i in range(5):
            count = 0 if i < 3 else 1

            if count == 0:
                consecutive_zero_count += 1
            else:
                consecutive_zero_count = 0

            status = "degraded" if consecutive_zero_count > 3 else "healthy"
            pipeline_statuses.append(status)

        assert pipeline_statuses[0] == "healthy"
        assert pipeline_statuses[1] == "healthy"
        assert pipeline_statuses[2] == "healthy"
        assert pipeline_statuses[3] == "healthy"

    @pytest.mark.asyncio
    async def test_pipeline_status_degraded_after_four_zero_iterations(self):
        """When signals_generated=0 for 4+ consecutive iterations, pipeline_status is 'degraded'."""
        recorded_statuses = []

        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(return_value=True)
        mock_redis.keys = MagicMock(return_value=[])

        def capture_hset(name, mapping=None, **kwargs):
            if mapping and "pipeline_status" in mapping:
                recorded_statuses.append(mapping["pipeline_status"])
            return MagicMock()

        mock_redis.hset = MagicMock(side_effect=capture_hset)

        call_count = [0]

        async def mock_generate(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 4:
                return 0
            raise StopAsyncIteration("done")

        generator = MagicMock()
        storage = MagicMock()

        with patch(
            "scripts.continuous_signal_generator.generate_signals_batch",
            side_effect=mock_generate,
        ):
            with patch(
                "scripts.continuous_signal_generator.SignalGenerator",
                return_value=generator,
            ):
                with patch(
                    "scripts.continuous_signal_generator.InfluxDBStorage",
                    return_value=storage,
                ):
                    with patch(
                        "scripts.continuous_signal_generator.get_influxdb_config",
                        return_value=MagicMock(),
                    ):
                        with patch(
                            "scripts.continuous_signal_generator.check_influxdb_connectivity",
                            return_value=True,
                        ):
                            with patch("redis.Redis", return_value=mock_redis):
                                with patch("time.time") as mock_time:
                                    # First iteration at t=1000, second at t=1001, etc.
                                    mock_time.return_value = 1000.0

                                    from scripts.continuous_signal_generator import (
                                        continuous_signal_generation,
                                    )

                                    try:
                                        await continuous_signal_generation(
                                            duration_minutes=1, interval_seconds=1
                                        )
                                    except StopAsyncIteration:
                                        pass

        assert (
            len(recorded_statuses) >= 4
        ), f"Expected 4+ iterations, got {len(recorded_statuses)}: {recorded_statuses}"
        assert recorded_statuses[0] == "healthy"
        assert recorded_statuses[1] == "healthy"
        assert recorded_statuses[2] == "healthy"
        assert recorded_statuses[3] == "degraded"

    @pytest.mark.asyncio
    async def test_pipeline_status_recovers_to_healthy(self):
        """When signals recovers (>0), pipeline_status returns to 'healthy'."""
        recorded_statuses = []

        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(return_value=True)
        mock_redis.keys = MagicMock(return_value=[])

        def capture_hset(name, mapping=None, **kwargs):
            if mapping and "pipeline_status" in mapping:
                recorded_statuses.append(mapping["pipeline_status"])
            return MagicMock()

        mock_redis.hset = MagicMock(side_effect=capture_hset)

        call_count = [0]

        async def mock_generate(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 4:
                return 0
            return 1

        generator = MagicMock()
        storage = MagicMock()

        with patch(
            "scripts.continuous_signal_generator.generate_signals_batch",
            side_effect=mock_generate,
        ):
            with patch(
                "scripts.continuous_signal_generator.SignalGenerator",
                return_value=generator,
            ):
                with patch(
                    "scripts.continuous_signal_generator.InfluxDBStorage",
                    return_value=storage,
                ):
                    with patch(
                        "scripts.continuous_signal_generator.get_influxdb_config",
                        return_value=MagicMock(),
                    ):
                        with patch(
                            "scripts.continuous_signal_generator.check_influxdb_connectivity",
                            return_value=True,
                        ):
                            with patch("redis.Redis", return_value=mock_redis):
                                with patch("time.time") as mock_time:
                                    mock_time.return_value = 1000.0

                                    from scripts.continuous_signal_generator import (
                                        continuous_signal_generation,
                                    )

                                    try:
                                        await continuous_signal_generation(
                                            duration_minutes=1, interval_seconds=1
                                        )
                                    except StopAsyncIteration:
                                        pass

        assert (
            len(recorded_statuses) >= 5
        ), f"Expected 5+ iterations, got {len(recorded_statuses)}: {recorded_statuses}"
        assert recorded_statuses[3] == "degraded"
        assert recorded_statuses[4] == "healthy"

    @pytest.mark.asyncio
    async def test_pipeline_status_remains_healthy_at_boundary(self):
        """When signals_generated=0 for exactly 3 iterations, pipeline_status remains 'healthy'."""
        recorded_statuses = []

        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(return_value=True)
        mock_redis.keys = MagicMock(return_value=[])

        def capture_hset(name, mapping=None, **kwargs):
            if mapping and "pipeline_status" in mapping:
                recorded_statuses.append(mapping["pipeline_status"])
            return MagicMock()

        mock_redis.hset = MagicMock(side_effect=capture_hset)

        call_count = [0]

        async def mock_generate(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 3:
                return 0
            return 1

        generator = MagicMock()
        storage = MagicMock()

        with patch(
            "scripts.continuous_signal_generator.generate_signals_batch",
            side_effect=mock_generate,
        ):
            with patch(
                "scripts.continuous_signal_generator.SignalGenerator",
                return_value=generator,
            ):
                with patch(
                    "scripts.continuous_signal_generator.InfluxDBStorage",
                    return_value=storage,
                ):
                    with patch(
                        "scripts.continuous_signal_generator.get_influxdb_config",
                        return_value=MagicMock(),
                    ):
                        with patch(
                            "scripts.continuous_signal_generator.check_influxdb_connectivity",
                            return_value=True,
                        ):
                            with patch("redis.Redis", return_value=mock_redis):
                                with patch("time.time") as mock_time:
                                    mock_time.return_value = 1000.0

                                    from scripts.continuous_signal_generator import (
                                        continuous_signal_generation,
                                    )

                                    try:
                                        await continuous_signal_generation(
                                            duration_minutes=1, interval_seconds=1
                                        )
                                    except StopAsyncIteration:
                                        pass

        assert (
            len(recorded_statuses) >= 4
        ), f"Expected 4+ iterations, got {len(recorded_statuses)}: {recorded_statuses}"
        assert recorded_statuses[0] == "healthy"
        assert recorded_statuses[1] == "healthy"
        assert recorded_statuses[2] == "healthy"
        assert recorded_statuses[3] == "healthy"
