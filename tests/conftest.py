import asyncio
import os
import subprocess

import pytest


class HostLeakError(AssertionError):
    """Raised when any test attempts to execute an unmocked host OS subprocess or command."""

    pass


def _deny_subprocess(*args, **kwargs):
    cmd = args[0] if args else kwargs.get("args", "unknown")
    raise HostLeakError(
        f"CRITICAL: Test attempted unmocked host OS execution: {cmd!r}. "
        f"All OS commands and subprocesses must be mocked or injected via ports."
    )


@pytest.fixture(autouse=True)
def enforce_hard_sandbox(monkeypatch, tmp_path, request):
    """
    Enforces absolute hermeticity for the test suite:
    1. Blocks all subprocess and shell execution functions (run, Popen, call, os.system, etc.).
    2. Isolates the HOME directory to a disposable temporary folder so tests never touch ~/.config, ~/.claude, etc.
    """
    # Allow opt-in for integration tests explicitly marked with os_integration (if any)
    if request.node.get_closest_marker("os_integration"):
        return

    # 1. Deny all subprocess entrypoints
    for name in ("run", "Popen", "call", "check_call", "check_output"):
        if hasattr(subprocess, name):
            monkeypatch.setattr(subprocess, name, _deny_subprocess)

    # 2. Deny os process entrypoints
    for name in (
        "system",
        "posix_spawn",
        "posix_spawnp",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
    ):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, _deny_subprocess)

    # 3. Deny asyncio subprocess entrypoints
    if hasattr(asyncio, "create_subprocess_exec"):
        monkeypatch.setattr(asyncio, "create_subprocess_exec", _deny_subprocess)
    if hasattr(asyncio, "create_subprocess_shell"):
        monkeypatch.setattr(asyncio, "create_subprocess_shell", _deny_subprocess)

    # 4. Sandbox HOME to a clean temporary path
    fake_home = tmp_path / "sandbox_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
