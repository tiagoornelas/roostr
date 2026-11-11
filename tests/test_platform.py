import sys
from unittest.mock import patch

import pytest

from roostr.infrastructure.launchd import LaunchdServiceAdapter
from roostr.infrastructure.notifier import LinuxNotifierAdapter, MacNotifierAdapter
from roostr.infrastructure.platform import (
    get_default_daemon_service,
    get_default_notifier,
    get_default_shell,
    get_default_terminal_target_adapter,
    is_linux,
    is_macos,
)
from roostr.infrastructure.systemd import SystemdUserServiceAdapter
from roostr.infrastructure.targets.linux_terminal import LinuxTerminalTargetAdapter
from roostr.infrastructure.targets.terminal import TerminalTargetAdapter


def test_platform_detection(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert is_macos() is True
    assert is_linux() is False

    monkeypatch.setattr(sys, "platform", "linux")
    assert is_macos() is False
    assert is_linux() is True


def test_get_default_daemon_service_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    svc = get_default_daemon_service()
    assert isinstance(svc, LaunchdServiceAdapter)


def test_get_default_daemon_service_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    svc = get_default_daemon_service()
    assert isinstance(svc, SystemdUserServiceAdapter)


def test_get_default_daemon_service_unsupported(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(NotImplementedError):
        get_default_daemon_service()


def test_get_default_notifier(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    notif_mac = get_default_notifier()
    assert isinstance(notif_mac, MacNotifierAdapter)

    monkeypatch.setattr(sys, "platform", "linux")
    notif_linux = get_default_notifier()
    assert isinstance(notif_linux, LinuxNotifierAdapter)


def test_get_default_terminal_adapter(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    term_mac = get_default_terminal_target_adapter()
    assert isinstance(term_mac, TerminalTargetAdapter)

    monkeypatch.setattr(sys, "platform", "linux")
    term_linux = get_default_terminal_target_adapter()
    assert isinstance(term_linux, LinuxTerminalTargetAdapter)


def test_get_default_shell(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/custom_shell")
    assert get_default_shell() == "/bin/custom_shell"

    monkeypatch.delenv("SHELL", raising=False)
    with patch("shutil.which", return_value="/bin/bash"):
        assert get_default_shell() == "/bin/bash"

    with patch("shutil.which", return_value=None):
        assert get_default_shell() == "/bin/sh"
