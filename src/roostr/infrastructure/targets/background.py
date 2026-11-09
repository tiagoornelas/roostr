import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.models import Job

DEFAULT_LOGS_DIR = Path.home() / ".local" / "state" / "roostr" / "logs"


class BackgroundTargetAdapter(ExecutionTargetPort):
    def __init__(
        self,
        logs_dir: Path = DEFAULT_LOGS_DIR,
        popen_fn: Callable[..., subprocess.Popen] | None = None,
    ):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._popen_fn = popen_fn or subprocess.Popen

    def launch(self, job: Job, dt: datetime) -> tuple[bool, str]:
        log_file = self.logs_dir / f"{job.id}-{dt.strftime('%Y%m%d')}.log"
        cmd = f"cd {job.cwd} && {job.command}"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n=== [roostr] Started at {dt.isoformat()} ===\n")
                process = self._popen_fn(
                    ["zsh", "-lic", cmd],
                    stdout=f,
                    stderr=f,
                    start_new_session=True,
                )
            return (
                True,
                f"Background process dispatched (PID {getattr(process, 'pid', 'unknown')}, log: {log_file.name})",
            )
        except Exception as e:
            return False, f"Failed to dispatch background process: {e}"
