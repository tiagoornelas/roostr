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


def test_parse_time_string():
    from roostr.domain.models import parse_time_string

    assert parse_time_string("08:00") == time(8, 0)
    assert parse_time_string("14:30") == time(14, 30)
    assert parse_time_string("7am") == time(7, 0)
    assert parse_time_string("7 AM") == time(7, 0)
    assert parse_time_string("9:30 am") == time(9, 30)
    assert parse_time_string("2:30 pm") == time(14, 30)
    assert parse_time_string("6pm") == time(18, 0)
    assert parse_time_string("12am") == time(0, 0)
    assert parse_time_string("12pm") == time(12, 0)


def test_parse_times_list():
    from roostr.domain.models import parse_times_list

    res = parse_times_list("7am, 9:30 am, 2:30 pm, 6pm")
    assert res == (time(7, 0), time(9, 30), time(14, 30), time(18, 0))

    res_empty = parse_times_list("")
    assert res_empty == (time(8, 0),)


def test_schedule_policy_multiple_times():
    p = SchedulePolicy(
        days_of_week=(0,),
        times_of_day=(time(7, 0), time(9, 30), time(14, 30), time(18, 0)),
        tolerance_mode=ToleranceMode.EXACT,
    )
    assert p.time_of_day == time(7, 0)
    assert p.is_within_window(datetime(2026, 11, 9, 7, 0)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 9, 30)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 14, 31)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 18, 0)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 10, 0)) is False


def test_schedule_policy_interval_window():
    from roostr.domain.enums import ScheduleFrequency

    p = SchedulePolicy(
        days_of_week=(0,),
        frequency=ScheduleFrequency.INTERVAL_HOURS,
        interval_value=2,
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    assert p.is_within_window(datetime(2026, 11, 9, 8, 59)) is False
    assert p.is_within_window(datetime(2026, 11, 9, 9, 0)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 14, 0)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 18, 0)) is True
    assert p.is_within_window(datetime(2026, 11, 9, 18, 1)) is False


def test_job_default_target_herdr():
    job = Job(
        id="test-default",
        name="Test Default",
        cwd="/tmp",
        schedule=SchedulePolicy((0,), time(9, 0)),
        command="echo hello",
    )
    assert isinstance(job.target, HerdrTargetConfig)
    assert job.target.space == "Roostr"


def test_schedule_policy_window_hours_and_until_hour_edge_cases():
    p_window = SchedulePolicy(
        days_of_week=(0,),
        time_of_day=time(9, 0),
        tolerance_mode=ToleranceMode.WINDOW_HOURS,
        tolerance_value=3,
    )
    # 09:00 to 12:00
    assert p_window.is_within_window(datetime(2026, 11, 9, 9, 0)) is True
    assert p_window.is_within_window(datetime(2026, 11, 9, 11, 59)) is True
    assert p_window.is_within_window(datetime(2026, 11, 9, 12, 0)) is False

    # until_hour where end_minutes <= start_minutes (e.g. start at 10:00, until 8:00 -> defaults to +60 min)
    p_until = SchedulePolicy(
        days_of_week=(0,),
        time_of_day=time(10, 0),
        tolerance_mode=ToleranceMode.UNTIL_HOUR,
        tolerance_value=8,
    )
    assert p_until.is_within_window(datetime(2026, 11, 9, 10, 30)) is True
    assert p_until.is_within_window(datetime(2026, 11, 9, 11, 1)) is False


def test_job_positional_constructors_and_validations():
    import pytest

    from roostr.domain.models import CommandAction

    sched = SchedulePolicy((0,), time(9, 0))
    target = TerminalTargetConfig()

    # Form 1: Job(id, name, cwd, command_str, schedule, target)
    j1 = Job("j1", "J1", "/tmp", "echo 1", sched, target)
    assert j1.command == "echo 1"

    # Form 2: Job(id, name, cwd, schedule, target, action)
    action = CommandAction("echo 2")
    j2 = Job("j2", "J2", "/tmp", sched, target, action)
    assert j2.command == "echo 2"

    # Missing schedule
    with pytest.raises(ValueError, match="Job requires a SchedulePolicy"):
        Job("j3", "J3", "/tmp", command="echo 3", schedule=None)  # type: ignore

    # Missing command and action
    with pytest.raises(ValueError, match="Job requires either an action or a command"):
        Job("j4", "J4", "/tmp", schedule=sched, target=target)

    # resolve_herdr_tab_name with terminal target
    assert j1.resolve_herdr_tab_name(datetime.now()) == "J1"

    # resolve_herdr_tab_name with HerdrTargetConfig without template
    herdr_job = Job("j_h", "JH", "/tmp", "echo 1", sched, HerdrTargetConfig(space="Roostr", tab_template=""))
    assert "JH" in herdr_job.resolve_herdr_tab_name(datetime.now())


def test_schedule_policy_unknown_tolerance_mode():
    sched = SchedulePolicy((0,), time(9, 0))
    sched.tolerance_mode = "unknown"  # type: ignore
    assert sched.is_time_within_slot_window(time(9, 0), datetime(2026, 11, 9, 9, 0)) is False
