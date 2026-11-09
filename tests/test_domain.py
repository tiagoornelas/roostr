from datetime import datetime, time

from roostr.domain.enums import TargetType, TerminalApp, ToleranceMode
from roostr.domain.models import (
    BackgroundTargetConfig,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)


def test_schedule_policy_is_active_on_day():
    policy = SchedulePolicy(
        days_of_week=(0, 1, 2, 3, 4),  # Mon-Fri
        time_of_day=time(8, 0),
        tolerance_mode=ToleranceMode.UNTIL_HOUR,
        tolerance_value=12,
    )
    assert policy.is_active_on_weekday(0) is True
    assert policy.is_active_on_weekday(4) is True
    assert policy.is_active_on_weekday(5) is False
    assert policy.is_active_on_weekday(6) is False


def test_schedule_policy_is_within_window_until_hour():
    policy = SchedulePolicy(
        days_of_week=(0, 1, 2, 3, 4),
        time_of_day=time(8, 0),
        tolerance_mode=ToleranceMode.UNTIL_HOUR,
        tolerance_value=12,
    )
    assert policy.is_within_window(datetime(2026, 11, 9, 8, 0)) is True
    assert policy.is_within_window(datetime(2026, 11, 9, 11, 59)) is True
    assert policy.is_within_window(datetime(2026, 11, 9, 12, 0)) is False
    assert policy.is_within_window(datetime(2026, 11, 9, 7, 59)) is False


def test_schedule_policy_exact_mode():
    policy = SchedulePolicy(
        days_of_week=(0, 1, 2, 3, 4),
        time_of_day=time(17, 0),
        tolerance_mode=ToleranceMode.EXACT,
        tolerance_value=0,
    )
    assert policy.is_within_window(datetime(2026, 11, 9, 17, 0)) is True
    assert policy.is_within_window(datetime(2026, 11, 9, 17, 1)) is True
    assert policy.is_within_window(datetime(2026, 11, 9, 17, 5)) is False


def test_target_configs():
    terminal_target = TerminalTargetConfig(app=TerminalApp.GHOSTTY, keep_open=True)
    assert terminal_target.target_type == TargetType.TERMINAL
    assert terminal_target.app == TerminalApp.GHOSTTY

    herdr_target = HerdrTargetConfig(space="Personal Coordinator", tab_template="Daily {DD}/{MM}")
    assert herdr_target.target_type == TargetType.HERDR
    assert herdr_target.space == "Personal Coordinator"

    bg_target = BackgroundTargetConfig(notify_on_complete=True)
    assert bg_target.target_type == TargetType.BACKGROUND


def test_job_folder_hierarchy():
    import pytest

    # Root job without folder
    job_none = Job(
        id="test-1",
        name="Test 1",
        cwd="/tmp",
        command="echo",
        schedule=SchedulePolicy(days_of_week=(0,), time_of_day=time(8, 0)),
        target=BackgroundTargetConfig(),
        folder=None,
    )
    assert job_none.root_folder is None
    assert job_none.subfolder is None

    # Level 1 folder
    job_l1 = Job(
        id="test-2",
        name="Test 2",
        cwd="/tmp",
        command="echo",
        schedule=SchedulePolicy(days_of_week=(0,), time_of_day=time(8, 0)),
        target=BackgroundTargetConfig(),
        folder="Work",
    )
    assert job_l1.root_folder == "Work"
    assert job_l1.subfolder is None

    # Level 2 folder
    job_l2 = Job(
        id="test-3",
        name="Test 3",
        cwd="/tmp",
        command="echo",
        schedule=SchedulePolicy(days_of_week=(0,), time_of_day=time(8, 0)),
        target=BackgroundTargetConfig(),
        folder="Work/Reports",
    )
    assert job_l2.root_folder == "Work"
    assert job_l2.subfolder == "Reports"

    # More than 2 levels raises ValueError
    with pytest.raises(ValueError, match="cannot exceed 2 levels"):
        Job(
            id="test-4",
            name="Test 4",
            cwd="/tmp",
            command="echo",
            schedule=SchedulePolicy(days_of_week=(0,), time_of_day=time(8, 0)),
            target=BackgroundTargetConfig(),
            folder="Work/Reports/Deep",
        )
