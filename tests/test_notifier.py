from unittest.mock import MagicMock

from roostr.infrastructure.notifier import LinuxNotifierAdapter, MacNotifierAdapter


def test_mac_notifier_adapter():
    runner_mock = MagicMock()
    adapter = MacNotifierAdapter(cmd_runner=runner_mock)
    adapter.notify("Test Title", "Test Message")

    assert runner_mock.call_count == 1
    args = runner_mock.call_args[0][0]
    assert args[0] == "osascript"
    assert "Test Title" in args[2]
    assert "Test Message" in args[2]


def test_linux_notifier_adapter():
    runner_mock = MagicMock()
    adapter = LinuxNotifierAdapter(cmd_runner=runner_mock)
    adapter.notify("Hello Linux", "Task completed")

    assert runner_mock.call_count == 1
    args = runner_mock.call_args[0][0]
    assert args == ["notify-send", "Hello Linux", "Task completed"]


def test_linux_notifier_adapter_handles_exceptions():
    runner_mock = MagicMock(side_effect=FileNotFoundError("notify-send not found"))
    adapter = LinuxNotifierAdapter(cmd_runner=runner_mock)
    # Should not raise exception
    adapter.notify("Title", "Message")
