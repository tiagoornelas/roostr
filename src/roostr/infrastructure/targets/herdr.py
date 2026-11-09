import json
import subprocess
import time
from collections.abc import Callable
from datetime import datetime

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.models import HerdrTargetConfig, Job


class HerdrTargetAdapter(ExecutionTargetPort):
    def __init__(
        self,
        cmd_runner: Callable[..., subprocess.CompletedProcess] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self._cmd_runner = cmd_runner or subprocess.run
        self._sleep_fn = sleep_fn or time.sleep

    def is_running(self) -> bool:
        try:
            res = self._cmd_runner(
                ["hc", "server", "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    def get_space_id(self, space_name: str) -> str | None:
        try:
            res = self._cmd_runner(
                ["herdr-app", "ls"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode != 0 or not res.stdout.strip():
                return None
            data = json.loads(res.stdout)
            for space in data.get("spaces", []):
                if space.get("name") == space_name:
                    return space.get("id")
        except Exception:
            pass
        return None

    def launch(self, job: Job, dt: datetime) -> tuple[bool, str]:
        if not self.is_running():
            return False, "Herdr is not running"

        if not isinstance(job.target, HerdrTargetConfig):
            return False, "Job target is not configured for Herdr"

        space_id = self.get_space_id(job.target.space)
        if not space_id:
            return False, f'Space "{job.target.space}" not found in Herdr'

        terminal_name = f"{job.id}-{dt.strftime('%Y%m%d')}"

        hc_cmd = [
            "hc",
            "run",
            "--bg",
            "--json",
            "--name",
            terminal_name,
            "--cwd",
            job.cwd,
            "--no-parent",
            "--outlive-parent",
            "--label",
            f"herdr.space={space_id}",
            "env",
            "TERM=xterm-256color",
            "zsh",
            "-lic",
            job.command,
        ]

        try:
            res = self._cmd_runner(hc_cmd, capture_output=True, text=True, timeout=10, check=False)
            if res.returncode != 0:
                return False, f"Failed to execute hc run: {res.stderr.strip()}"
        except Exception as e:
            return False, f"Error spawning hc process: {e}"

        tab_label = job.resolve_herdr_tab_name(dt)
        tab_id = self._find_tab_id_for_terminal(terminal_name, retries=10)
        if tab_id:
            try:
                self._cmd_runner(
                    ["herdr-app", "do", "tab.rename", "--id", tab_id, "--name", tab_label],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                pass
            return True, f"Opened terminal {terminal_name} in tab {tab_id} ('{tab_label}')"

        return True, f"Opened terminal {terminal_name} in space '{job.target.space}'"

    def _find_tab_id_for_terminal(self, terminal_name: str, retries: int = 10) -> str | None:
        for _ in range(retries):
            try:
                res = self._cmd_runner(
                    ["herdr-app", "ls"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    data = json.loads(res.stdout)
                    for space in data.get("spaces", []):
                        for tab in space.get("tabs", []):
                            if any(t.get("name") == terminal_name for t in tab.get("terminals", [])):
                                return tab.get("id")
            except Exception:
                pass
            self._sleep_fn(1)
        return None
