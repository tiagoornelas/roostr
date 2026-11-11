import os
import shutil
import sys

from roostr.application.ports import DaemonServicePort, ExecutionTargetPort, NotificationPort


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def get_default_shell() -> str:
    env_shell = os.environ.get("SHELL")
    if env_shell:
        return env_shell

    for candidate in ("bash", "sh", "zsh"):
        found = shutil.which(candidate)
        if found:
            return found

    return "/bin/sh"


def get_default_daemon_service() -> DaemonServicePort:
    if is_macos():
        from roostr.infrastructure.launchd import LaunchdServiceAdapter

        return LaunchdServiceAdapter()
    elif is_linux() or sys.platform.startswith("freebsd") or sys.platform.startswith("openbsd"):
        from roostr.infrastructure.systemd import SystemdUserServiceAdapter

        return SystemdUserServiceAdapter()
    else:
        raise NotImplementedError(f"Unsupported operating system for background daemon: {sys.platform}")


def get_default_notifier() -> NotificationPort:
    if is_macos():
        from roostr.infrastructure.notifier import MacNotifierAdapter

        return MacNotifierAdapter()
    else:
        from roostr.infrastructure.notifier import LinuxNotifierAdapter

        return LinuxNotifierAdapter()


def get_default_terminal_target_adapter() -> ExecutionTargetPort:
    if is_macos():
        from roostr.infrastructure.targets.terminal import TerminalTargetAdapter

        return TerminalTargetAdapter()
    else:
        from roostr.infrastructure.targets.linux_terminal import LinuxTerminalTargetAdapter

        return LinuxTerminalTargetAdapter()
