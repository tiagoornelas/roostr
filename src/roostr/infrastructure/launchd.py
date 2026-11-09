import os
import plistlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from roostr.application.ports import SchedulerPort
from roostr.domain.models import Job

DEFAULT_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_LOGS_DIR = Path.home() / "Library" / "Logs"


class LaunchdSchedulerAdapter(SchedulerPort):
    def __init__(
        self,
        agents_dir: Path = DEFAULT_AGENTS_DIR,
        logs_dir: Path = DEFAULT_LOGS_DIR,
        binary_path: Path | None = None,
        cmd_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    ):
        self.agents_dir = agents_dir
        self.logs_dir = logs_dir
        self._binary_path = binary_path or self._discover_binary()
        self._cmd_runner = cmd_runner or subprocess.run

    def _discover_binary(self) -> Path:
        local_bin = Path.home() / ".local" / "bin" / "roostr"
        if local_bin.exists():
            return local_bin
        found = shutil.which("roostr")
        if found:
            return Path(found)
        return Path("/usr/local/bin/roostr")

    def get_label(self, job_id: str) -> str:
        return f"com.tiagoornelas.roostr.{job_id}"

    def get_plist_path(self, job_id: str) -> Path:
        return self.agents_dir / f"{self.get_label(job_id)}.plist"

    def get_log_path(self, job_id: str) -> Path:
        return self.logs_dir / f"roostr-{job_id}.log"

    def generate_plist_xml(self, job: Job) -> str:
        intervals = []
        for wd in job.schedule.days_of_week:
            intervals.append(
                {
                    "Weekday": wd + 1,
                    "Hour": job.schedule.time_of_day.hour,
                    "Minute": job.schedule.time_of_day.minute,
                }
            )

        log_file = str(self.get_log_path(job.id))
        env_path = os.environ.get(
            "PATH",
            f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        )
        if str(Path.home() / ".local/bin") not in env_path:
            env_path = f"{Path.home()}/.local/bin:{env_path}"

        plist_data = {
            "Label": self.get_label(job.id),
            "ProgramArguments": [str(self._binary_path), "run", job.id],
            "StartCalendarInterval": intervals,
            "RunAtLoad": True,
            "StandardOutPath": log_file,
            "StandardErrorPath": log_file,
            "EnvironmentVariables": {
                "PATH": env_path,
            },
        }
        return plistlib.dumps(plist_data).decode("utf-8")

    def install(self, job: Job) -> Path:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        plist_path = self.get_plist_path(job.id)
        xml = self.generate_plist_xml(job)
        plist_path.write_text(xml, encoding="utf-8")

        try:
            self._cmd_runner(["launchctl", "unload", "-w", str(plist_path)])
        except Exception:
            pass
        self._cmd_runner(["launchctl", "load", "-w", str(plist_path)])
        return plist_path

    def uninstall(self, job_id: str) -> None:
        plist_path = self.get_plist_path(job_id)
        if plist_path.exists():
            try:
                self._cmd_runner(["launchctl", "unload", "-w", str(plist_path)])
            except Exception:
                pass
            plist_path.unlink(missing_ok=True)

    def pause(self, job_id: str) -> None:
        plist_path = self.get_plist_path(job_id)
        if plist_path.exists():
            try:
                self._cmd_runner(["launchctl", "unload", "-w", str(plist_path)])
            except Exception:
                pass

    def resume(self, job: Job) -> None:
        plist_path = self.get_plist_path(job.id)
        if not plist_path.exists():
            self.install(job)
        else:
            try:
                self._cmd_runner(["launchctl", "load", "-w", str(plist_path)])
            except Exception:
                pass
