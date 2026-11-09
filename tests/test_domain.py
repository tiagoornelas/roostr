import shlex
from datetime import datetime, time

from roostr.domain.enums import ActionType, AIHarness, TargetType, TerminalApp, ToleranceMode
from roostr.domain.models import (
    HARNESS_INFO,
    AgentAction,
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


def test_agent_action_compilation():
    prompt = "Review PRs.\nDon't forget tests!"
    action_claude = AgentAction(harness=AIHarness.CLAUDE, prompt=prompt)
    action_agy = AgentAction(harness=AIHarness.ANTIGRAVITY, prompt=prompt)
    action_cursor = AgentAction(harness=AIHarness.CURSOR, prompt=prompt)
    action_codex = AgentAction(harness=AIHarness.CODEX, prompt=prompt)

    assert action_claude.action_type == ActionType.AGENT
    assert f"claude {shlex.quote(prompt.strip())}" == action_claude.compile()
    assert f"agy {shlex.quote(prompt.strip())}" == action_agy.compile()
    assert f"cursor {shlex.quote(prompt.strip())}" == action_cursor.compile()
    assert f"codex {shlex.quote(prompt.strip())}" == action_codex.compile()


def test_job_with_agent_action():
    job = Job(
        id="daily-agent",
        name="Daily AI Agent",
        cwd="/tmp",
        schedule=SchedulePolicy((0,), time(9, 0)),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
        action=AgentAction(harness=AIHarness.ANTIGRAVITY, prompt="agy prompt"),
    )
    assert job.command == "agy 'agy prompt'"
    assert job.action.action_type == ActionType.AGENT
    assert isinstance(job.action, AgentAction)
    assert HARNESS_INFO[job.action.harness].display_name == "Antigravity"


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


def test_harness_info_colors_and_no_emojis():
    # Claude: orange
    assert HARNESS_INFO[AIHarness.CLAUDE].color == "#F97316"
    assert HARNESS_INFO[AIHarness.CLAUDE].symbol == ""

    # Antigravity: blue
    assert HARNESS_INFO[AIHarness.ANTIGRAVITY].color == "#3B82F6"
    assert HARNESS_INFO[AIHarness.ANTIGRAVITY].symbol == ""

    # Cursor: dark gray
    assert HARNESS_INFO[AIHarness.CURSOR].color == "#94A3B8"
    assert HARNESS_INFO[AIHarness.CURSOR].symbol == ""

    # Codex: white
    assert HARNESS_INFO[AIHarness.CODEX].color == "#FFFFFF"
    assert HARNESS_INFO[AIHarness.CODEX].symbol == ""


def test_slugify_sanitization():
    from roostr.domain.models import slugify

    assert slugify("Daily Code Review") == "daily-code-review"
    assert slugify("Relatório Matinal 09/11!") == "relatorio-matinal-09-11"
    assert slugify("  Multiple   Spaces & Symbols --- ") == "multiple-spaces-symbols"
    assert slugify("Ação & Reação: Teste 100%") == "acao-reacao-teste-100"
    assert slugify("") == "job"


def test_schedule_policy_frequencies():
    from roostr.domain.enums import ScheduleFrequency

    # Interval frequency is always within window regardless of time of day
    p_hours = SchedulePolicy(
        days_of_week=(0, 1),
        frequency=ScheduleFrequency.INTERVAL_HOURS,
        interval_value=2,
    )
    assert p_hours.is_within_window(datetime(2026, 11, 9, 3, 15)) is True

    p_mins = SchedulePolicy(
        days_of_week=(0, 1),
        frequency=ScheduleFrequency.INTERVAL_MINUTES,
        interval_value=30,
    )
    assert p_mins.is_within_window(datetime(2026, 11, 9, 23, 59)) is True
