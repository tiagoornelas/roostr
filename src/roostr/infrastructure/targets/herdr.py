import json
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.models import HerdrTargetConfig, Job

ROOSTR_SVG_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2a4 4 0 0 0-4 4v1a4 4 0 0 0 1 2.6L7 12l2 2-3 2 4 4h8l2-4-2-2 1-3.4A4 4 0 0 0 16 7V6a4 4 0 0 0-4-4z"/>
  <path d="M12 2c1 1 1 3 0 4"/>
  <path d="M9 6a1.5 1.5 0 0 1 3-1"/>
  <circle cx="10" cy="8" r="1" fill="currentColor"/>
  <path d="m14 10 3 1-3 1"/>
  <path d="M11 13c1 1 2 1 2 3"/>
</svg>"""


def register_herdr_program(config_dir: Path | None = None) -> bool:
    """Registers roostr in Herdr App's programs.json and writes rooster SVG icon."""
    herdr_dir = config_dir or (Path.home() / ".config" / "herdr-app")
    if not herdr_dir.exists():
        return False

    try:
        icons_dir = herdr_dir / "icons"
        icons_dir.mkdir(parents=True, exist_ok=True)
        roostr_icon_file = icons_dir / "roostr.svg"
        if not roostr_icon_file.exists():
            roostr_icon_file.write_text(ROOSTR_SVG_ICON, encoding="utf-8")

        programs_file = herdr_dir / "programs.json"
        programs_data: dict = {"programs": {}}
        if programs_file.exists():
            try:
                programs_data = json.loads(programs_file.read_text(encoding="utf-8"))
            except Exception:
                programs_data = {"programs": {}}

        if "programs" not in programs_data or not isinstance(programs_data["programs"], dict):
            programs_data["programs"] = {}

        programs_data["programs"]["roostr"] = {
            "name": "Roostr",
            "icon": "icons/roostr.svg",
            "tint": True,
            "tile": "#ff5722",
            "color": "#ffffff",
            "match": ["roostr"],
        }

        programs_file.write_text(json.dumps(programs_data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


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
