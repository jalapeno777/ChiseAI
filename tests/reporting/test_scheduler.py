"""Tests for scheduler.py"""

from datetime import datetime

from src.reporting.core.scheduler import (
    ReportPeriod,
    ReportScheduler,
    ReportTrigger,
)


class TestReportTrigger:
    """Test suite for ReportTrigger"""

    def test_should_run_daily(self):
        """Test daily trigger should_run"""
        trigger = ReportTrigger(period=ReportPeriod.DAILY, hour=9, minute=0)
        # Last run was yesterday, should run today
        yesterday = datetime(2026, 3, 28, 9, 0)
        today_same_time = datetime(2026, 3, 29, 9, 0)
        trigger.last_run = yesterday
        assert trigger.should_run(today_same_time) is True

    def test_should_run_disabled(self):
        """Test disabled trigger should_run returns False"""
        trigger = ReportTrigger(
            period=ReportPeriod.DAILY, hour=9, minute=0, enabled=False
        )
        now = datetime(2026, 3, 29, 9, 0)
        assert trigger.should_run(now) is False

    def test_should_run_daily_not_yet_time(self):
        """Test daily trigger at wrong time"""
        trigger = ReportTrigger(period=ReportPeriod.DAILY, hour=9, minute=0)
        now = datetime(2026, 3, 29, 10, 0)  # 10:00 instead of 9:00
        assert trigger.should_run(now) is False

    def test_should_run_weekly_monday(self):
        """Test weekly trigger on Monday"""
        trigger = ReportTrigger(period=ReportPeriod.WEEKLY, hour=9, minute=0)
        # Monday March 30, 2026
        now = datetime(2026, 3, 30, 9, 0)
        trigger.last_run = datetime(2026, 3, 23, 9, 0)  # Previous Monday
        assert trigger.should_run(now) is True

    def test_should_run_weekly_not_monday(self):
        """Test weekly trigger not on Monday"""
        trigger = ReportTrigger(period=ReportPeriod.WEEKLY, hour=9, minute=0)
        # Tuesday March 31, 2026
        now = datetime(2026, 3, 31, 9, 0)
        trigger.last_run = datetime(2026, 3, 23, 9, 0)
        assert trigger.should_run(now) is False

    def test_should_run_monthly_first_day(self):
        """Test monthly trigger on 1st of month"""
        trigger = ReportTrigger(period=ReportPeriod.MONTHLY, hour=9, minute=0)
        now = datetime(2026, 4, 1, 9, 0)
        trigger.last_run = datetime(2026, 3, 1, 9, 0)
        assert trigger.should_run(now) is True

    def test_should_run_monthly_not_first(self):
        """Test monthly trigger not on 1st"""
        trigger = ReportTrigger(period=ReportPeriod.MONTHLY, hour=9, minute=0)
        now = datetime(2026, 3, 15, 9, 0)
        trigger.last_run = datetime(2026, 2, 1, 9, 0)
        assert trigger.should_run(now) is False


class TestReportScheduler:
    """Test suite for ReportScheduler"""

    def setup_method(self):
        """Set up test fixtures"""
        self.scheduler = ReportScheduler(output_dir="/tmp/reports", check_interval=60)

    def test_initialization(self):
        """Test scheduler initializes"""
        assert self.scheduler is not None
        assert self.scheduler._output_dir == "/tmp/reports"
        assert self.scheduler._check_interval == 60
        assert len(self.scheduler.triggers) == 0

    def test_add_trigger(self):
        """Test adding a trigger"""
        trigger = self.scheduler.add_trigger(
            period=ReportPeriod.DAILY,
            hour=9,
            minute=0,
            name="test_daily",
        )
        assert trigger is not None
        assert trigger.name == "test_daily"
        assert len(self.scheduler.triggers) == 1

    def test_schedule_daily(self):
        """Test scheduling daily trigger via helper"""
        trigger = self.scheduler.schedule_daily(hour=8, name="morning_report")
        assert trigger.period == ReportPeriod.DAILY
        assert trigger.hour == 8

    def test_schedule_weekly(self):
        """Test scheduling weekly trigger via helper"""
        trigger = self.scheduler.schedule_weekly(hour=10, name="weekly_summary")
        assert trigger.period == ReportPeriod.WEEKLY
        assert trigger.hour == 10

    def test_schedule_monthly(self):
        """Test scheduling monthly trigger via helper"""
        trigger = self.scheduler.schedule_monthly(hour=11, name="monthly_report")
        assert trigger.period == ReportPeriod.MONTHLY
        assert trigger.hour == 11

    def test_remove_trigger(self):
        """Test removing a trigger"""
        self.scheduler.add_trigger(period=ReportPeriod.DAILY, name="to_remove")
        result = self.scheduler.remove_trigger("to_remove")
        assert result is True
        assert len(self.scheduler.triggers) == 0

    def test_remove_trigger_not_found(self):
        """Test removing non-existent trigger"""
        result = self.scheduler.remove_trigger("non_existent")
        assert result is False

    def test_get_trigger(self):
        """Test getting a trigger by name"""
        self.scheduler.add_trigger(period=ReportPeriod.DAILY, name="test_get")
        trigger = self.scheduler.get_trigger("test_get")
        assert trigger is not None
        assert trigger.name == "test_get"

    def test_get_trigger_not_found(self):
        """Test getting non-existent trigger"""
        trigger = self.scheduler.get_trigger("non_existent")
        assert trigger is None

    def test_trigger_count(self):
        """Test trigger count via len(triggers)"""
        assert len(self.scheduler.triggers) == 0
        self.scheduler.add_trigger(period=ReportPeriod.DAILY, name="count_test_1")
        self.scheduler.add_trigger(period=ReportPeriod.WEEKLY, name="count_test_2")
        assert len(self.scheduler.triggers) == 2


class TestReportPeriod:
    """Test suite for ReportPeriod enum"""

    def test_values(self):
        """Test enum values"""
        assert ReportPeriod.DAILY.value == "daily"
        assert ReportPeriod.WEEKLY.value == "weekly"
        assert ReportPeriod.MONTHLY.value == "monthly"
