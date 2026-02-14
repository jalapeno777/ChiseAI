"""Tests for optimization scheduler module."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ml.scheduler import (
    JobStatus,
    OptimizationRecord,
    OptimizationScheduler,
    ParameterDelta,
    ScheduleConfig,
    ScheduleFrequency,
    ScheduledJob,
    VolatilityMonitor,
    VolatilityRegime,
)


class TestScheduleConfig:
    """Tests for ScheduleConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ScheduleConfig()

        assert config.frequency == ScheduleFrequency.WEEKLY
        assert config.day_of_week == 0  # Monday
        assert config.day_of_month == 1
        assert config.hour == 2  # 2 AM
        assert config.minute == 0
        assert config.timezone == "UTC"
        assert config.adaptive_enabled is True
        assert config.max_concurrent_jobs == 3

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            day_of_week=3,  # Thursday
            hour=14,
            minute=30,
        )

        assert config.frequency == ScheduleFrequency.DAILY
        assert config.day_of_week == 3
        assert config.hour == 14
        assert config.minute == 30

    def test_invalid_day_of_week_raises(self) -> None:
        """Test that invalid day_of_week raises ValueError."""
        with pytest.raises(ValueError, match="day_of_week must be 0-6"):
            ScheduleConfig(day_of_week=7)

    def test_invalid_day_of_month_raises(self) -> None:
        """Test that invalid day_of_month raises ValueError."""
        with pytest.raises(ValueError, match="day_of_month must be 1-31"):
            ScheduleConfig(day_of_month=32)

    def test_invalid_hour_raises(self) -> None:
        """Test that invalid hour raises ValueError."""
        with pytest.raises(ValueError, match="hour must be 0-23"):
            ScheduleConfig(hour=24)


class TestScheduledJob:
    """Tests for ScheduledJob class."""

    def test_job_creation(self) -> None:
        """Test job creation."""
        job = ScheduledJob(
            job_id="test_job",
            strategy_id="test_strategy",
            status=JobStatus.SCHEDULED,
        )

        assert job.job_id == "test_job"
        assert job.strategy_id == "test_strategy"
        assert job.status == JobStatus.SCHEDULED
        assert job.run_count == 0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        job = ScheduledJob(
            job_id="test_job",
            strategy_id="test_strategy",
            config=ScheduleConfig(frequency=ScheduleFrequency.DAILY),
        )

        data = job.to_dict()

        assert data["job_id"] == "test_job"
        assert data["strategy_id"] == "test_strategy"
        assert data["config"]["frequency"] == "daily"
        assert data["status"] == "scheduled"

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "job_id": "test_job",
            "strategy_id": "test_strategy",
            "status": "scheduled",
            "config": {
                "frequency": "weekly",
                "day_of_week": 1,
                "hour": 10,
            },
            "run_count": 5,
            "success_count": 4,
            "failure_count": 1,
        }

        job = ScheduledJob.from_dict(data)

        assert job.job_id == "test_job"
        assert job.run_count == 5
        assert job.config.frequency == ScheduleFrequency.WEEKLY
        assert job.config.day_of_week == 1


class TestParameterDelta:
    """Tests for ParameterDelta class."""

    def test_delta_creation(self) -> None:
        """Test delta creation."""
        delta = ParameterDelta(
            parameter_name="learning_rate",
            old_value=0.01,
            new_value=0.02,
            absolute_change=0.01,
            percent_change=100.0,
            significant=True,
        )

        assert delta.parameter_name == "learning_rate"
        assert delta.percent_change == 100.0
        assert delta.significant is True

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        delta = ParameterDelta(
            parameter_name="param",
            old_value=1,
            new_value=2,
        )

        data = delta.to_dict()

        assert data["parameter_name"] == "param"
        assert data["old_value"] == 1
        assert data["new_value"] == 2


class TestOptimizationRecord:
    """Tests for OptimizationRecord class."""

    def test_record_creation(self) -> None:
        """Test record creation."""
        record = OptimizationRecord(
            record_id="record_1",
            strategy_id="strategy_1",
            job_id="job_1",
            status=JobStatus.COMPLETED,
            new_score=1.5,
            improvement_pct=25.0,
        )

        assert record.record_id == "record_1"
        assert record.new_score == 1.5
        assert record.improvement_pct == 25.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        record = OptimizationRecord(
            record_id="record_1",
            strategy_id="strategy_1",
            job_id="job_1",
            status=JobStatus.COMPLETED,
        )

        data = record.to_dict()

        assert data["record_id"] == "record_1"
        assert data["status"] == "completed"
        assert data["volatility_regime"] == "normal"

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "record_id": "record_1",
            "strategy_id": "strategy_1",
            "job_id": "job_1",
            "status": "completed",
            "started_at": datetime.utcnow().isoformat(),
            "previous_parameters": {"x": 1.0},
            "new_parameters": {"x": 1.5},
            "previous_score": 1.0,
            "new_score": 1.5,
            "improvement_pct": 50.0,
            "volatility_regime": "high",
            "parameter_deltas": [
                {
                    "parameter_name": "x",
                    "old_value": 1.0,
                    "new_value": 1.5,
                    "absolute_change": 0.5,
                    "percent_change": 50.0,
                }
            ],
        }

        record = OptimizationRecord.from_dict(data)

        assert record.record_id == "record_1"
        assert record.volatility_regime == VolatilityRegime.HIGH
        assert len(record.parameter_deltas) == 1
        assert record.parameter_deltas[0].parameter_name == "x"


class TestVolatilityMonitor:
    """Tests for VolatilityMonitor class."""

    def test_default_regime(self) -> None:
        """Test default volatility regime."""
        monitor = VolatilityMonitor()

        # Should return NORMAL by default
        assert monitor._current_regime == VolatilityRegime.NORMAL

    def test_regime_update(self) -> None:
        """Test regime update."""
        monitor = VolatilityMonitor()

        monitor.update_regime(VolatilityRegime.HIGH)

        assert monitor._current_regime == VolatilityRegime.HIGH
        assert monitor._last_update is not None

    def test_should_run_in_high_volatility(self) -> None:
        """Test that optimization runs in high volatility."""
        monitor = VolatilityMonitor()
        monitor.update_regime(VolatilityRegime.HIGH)

        config = ScheduleConfig(adaptive_enabled=True, high_volatility_boost=True)

        should_run = monitor.should_run_optimization(ScheduleFrequency.WEEKLY, config)

        assert should_run is True

    def test_should_skip_in_low_volatility(self) -> None:
        """Test that optimization can be skipped in low volatility."""
        monitor = VolatilityMonitor()
        monitor.update_regime(VolatilityRegime.LOW)

        config = ScheduleConfig(adaptive_enabled=True, low_volatility_skip=True)

        should_run = monitor.should_run_optimization(ScheduleFrequency.WEEKLY, config)

        assert should_run is False

    def test_always_run_in_extreme_volatility(self) -> None:
        """Test that optimization always runs in extreme volatility."""
        monitor = VolatilityMonitor()
        monitor.update_regime(VolatilityRegime.EXTREME)

        config = ScheduleConfig(adaptive_enabled=True)

        should_run = monitor.should_run_optimization(ScheduleFrequency.WEEKLY, config)

        assert should_run is True


class TestOptimizationScheduler:
    """Tests for OptimizationScheduler class."""

    @pytest.fixture
    def temp_persistence_path(self):
        """Create a temporary persistence path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        yield path
        # Cleanup
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def scheduler(self, temp_persistence_path):
        """Create a scheduler with temporary persistence."""
        config = ScheduleConfig(persistence_path=temp_persistence_path)
        scheduler = OptimizationScheduler(config)
        yield scheduler
        # Cleanup
        if scheduler._running:
            asyncio.get_event_loop().run_until_complete(scheduler.stop())

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self, scheduler) -> None:
        """Test scheduler start and stop."""
        await scheduler.start()
        assert scheduler._running is True

        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_schedule_strategy(self, scheduler) -> None:
        """Test scheduling a strategy."""
        await scheduler.start()

        async def mock_task(strategy_id, previous_params):
            return {"x": 1.0}, 1.5, {"sharpe": 1.5}

        job = await scheduler.schedule_strategy(
            strategy_id="test_strategy",
            optimization_task=mock_task,
            config=ScheduleConfig(frequency=ScheduleFrequency.DAILY),
        )

        assert job.strategy_id == "test_strategy"
        assert job.job_id in scheduler._jobs
        assert scheduler._optimization_functions[job.job_id] == mock_task

    @pytest.mark.asyncio
    async def test_unschedule_strategy(self, scheduler) -> None:
        """Test unscheduling a strategy."""
        await scheduler.start()

        job = await scheduler.schedule_strategy(
            strategy_id="test_strategy",
            optimization_task=lambda s, p: ({}, 0, {}),
        )

        result = await scheduler.unschedule_strategy(job.job_id)

        assert result is True
        assert job.job_id not in scheduler._jobs

    @pytest.mark.asyncio
    async def test_pause_resume_job(self, scheduler) -> None:
        """Test pausing and resuming a job."""
        await scheduler.start()

        job = await scheduler.schedule_strategy(
            strategy_id="test_strategy",
            optimization_task=lambda s, p: ({}, 0, {}),
        )

        # Pause
        paused = await scheduler.pause_job(job.job_id)
        assert paused is True
        assert scheduler._jobs[job.job_id].status == JobStatus.PAUSED

        # Resume
        resumed = await scheduler.resume_job(job.job_id)
        assert resumed is True
        assert scheduler._jobs[job.job_id].status == JobStatus.SCHEDULED

    @pytest.mark.asyncio
    async def test_get_job(self, scheduler) -> None:
        """Test getting a job by ID."""
        await scheduler.start()

        job = await scheduler.schedule_strategy(
            strategy_id="test_strategy",
            optimization_task=lambda s, p: ({}, 0, {}),
        )

        retrieved = scheduler.get_job(job.job_id)

        assert retrieved is not None
        assert retrieved.job_id == job.job_id

    @pytest.mark.asyncio
    async def test_get_all_jobs(self, scheduler) -> None:
        """Test getting all jobs."""
        await scheduler.start()

        await scheduler.schedule_strategy(
            strategy_id="strategy_1",
            optimization_task=lambda s, p: ({}, 0, {}),
        )
        await scheduler.schedule_strategy(
            strategy_id="strategy_2",
            optimization_task=lambda s, p: ({}, 0, {}),
        )

        jobs = scheduler.get_all_jobs()

        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_run_job_now(self, scheduler) -> None:
        """Test manually running a job."""
        await scheduler.start()

        async def mock_task(strategy_id, previous_params):
            return {"x": 2.0}, 2.0, {"sharpe": 2.0}

        job = await scheduler.schedule_strategy(
            strategy_id="test_strategy",
            optimization_task=mock_task,
        )

        record = await scheduler.run_job_now(job.job_id)

        assert record is not None
        assert record.strategy_id == "test_strategy"
        assert record.status == JobStatus.COMPLETED
        assert record.new_score == 2.0

    def test_calculate_next_run_daily(self) -> None:
        """Test calculating next run time for daily schedule."""
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY, hour=10)
        scheduler = OptimizationScheduler(config)

        next_run = scheduler._calculate_next_run(config)

        assert next_run.hour == 10
        assert next_run.minute == 0

    def test_calculate_next_run_weekly(self) -> None:
        """Test calculating next run time for weekly schedule."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=0,  # Monday
            hour=10,
        )
        scheduler = OptimizationScheduler(config)

        next_run = scheduler._calculate_next_run(config)

        assert next_run.weekday() == 0  # Monday
        assert next_run.hour == 10

    def test_calculate_next_run_monthly(self) -> None:
        """Test calculating next run time for monthly schedule."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=15,
            hour=10,
        )
        scheduler = OptimizationScheduler(config)

        next_run = scheduler._calculate_next_run(config)

        assert next_run.day == 15
        assert next_run.hour == 10

    def test_calculate_deltas(self) -> None:
        """Test calculating parameter deltas."""
        scheduler = OptimizationScheduler()

        old_params = {"x": 1.0, "y": 10}
        new_params = {"x": 1.5, "y": 10, "z": 5}

        deltas = scheduler._calculate_deltas(old_params, new_params)

        assert len(deltas) == 2  # x changed, z added

        x_delta = next(d for d in deltas if d.parameter_name == "x")
        assert x_delta.old_value == 1.0
        assert x_delta.new_value == 1.5
        assert x_delta.absolute_change == 0.5
        assert x_delta.percent_change == 50.0

    def test_persistence_save_load(self, temp_persistence_path) -> None:
        """Test saving and loading scheduler state."""
        config = ScheduleConfig(persistence_path=temp_persistence_path)
        scheduler1 = OptimizationScheduler(config)

        # Add some jobs
        job1 = ScheduledJob(
            job_id="job_1",
            strategy_id="strategy_1",
            config=config,
        )
        scheduler1._jobs["job_1"] = job1

        # Save state
        scheduler1._save_state()

        # Create new scheduler and load
        scheduler2 = OptimizationScheduler(config)

        assert "job_1" in scheduler2._jobs
        assert scheduler2._jobs["job_1"].strategy_id == "strategy_1"

    def test_get_schedule_summary(self) -> None:
        """Test getting schedule summary."""
        config = ScheduleConfig()
        scheduler = OptimizationScheduler(config)

        # Add some jobs
        scheduler._jobs["job_1"] = ScheduledJob(
            job_id="job_1",
            strategy_id="strategy_1",
            config=config,
            next_run_at=datetime.utcnow() + timedelta(hours=1),
        )

        summary = scheduler.get_schedule_summary()

        assert summary["scheduler_running"] is False
        assert summary["total_jobs"] == 1
        assert len(summary["upcoming_runs"]) == 1


class TestScheduleFrequency:
    """Tests for ScheduleFrequency enum."""

    def test_frequency_values(self) -> None:
        """Test frequency enum values."""
        assert ScheduleFrequency.DAILY.value == "daily"
        assert ScheduleFrequency.WEEKLY.value == "weekly"
        assert ScheduleFrequency.MONTHLY.value == "monthly"
        assert ScheduleFrequency.VOLATILITY_ADAPTIVE.value == "volatility_adaptive"
        assert ScheduleFrequency.MANUAL.value == "manual"


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert JobStatus.SCHEDULED.value == "scheduled"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.PAUSED.value == "paused"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestVolatilityRegime:
    """Tests for VolatilityRegime enum."""

    def test_regime_values(self) -> None:
        """Test regime enum values."""
        assert VolatilityRegime.LOW.value == "low"
        assert VolatilityRegime.NORMAL.value == "normal"
        assert VolatilityRegime.HIGH.value == "high"
        assert VolatilityRegime.EXTREME.value == "extreme"
