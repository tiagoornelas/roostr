import os
import shlex
import shutil
import stat
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.enums import TerminalApp
from roostr.domain.models import Job, TerminalTargetConfig

DEFAULT_RUNNERS_DIR = Path.home() / ".local" / "state" / "roostr" / "runners"

# Supported Linux terminals and their argument patterns
TERMINAL_SPECS: dict[str, list[str]] = {
    "ghostty": ["-e"],
    "kitty": ["--"],
    "alacritty": ["-e"],
    "gnome-terminal": ["--"],
    "x-terminal-emulator": ["-e"],
    "konsole": ["-e"],
    "xfce4-terminal": ["-e"],
    "xterm": ["-e"],
}


class LinuxTerminalTargetAdapter(ExecutionTargetPort):
    def __init__(
        self,
        runners_dir: Path = DEFAULT_RUNNERS_DIR,
        cmd_runner: Callable[..., subprocess.CompletedProcess] | None = None,
        which_fn: Callable[[str], str | None] | None = None,
    ):
        self.runners_dir = runners_dir
        self.runners_dir.mkdir(parents=True, exist_ok=True)
        self._cmd_runner = cmd_runner or subprocess.run
        self._which = which_fn or shutil.which

    def generate_runner_script(self, job: Job) -> Path:
        script_path = self.runners_dir / f"{job.id}.sh"
        keep_open = isinstance(job.target, TerminalTargetConfig) and job.target.keep_open
        shell_path = os.environ.get("SHELL", "/bin/sh")
        tail_clause = f"exec {shell_path} -l\n" if keep_open else ""
        quoted_cwd = shlex.quote(str(job.cwd))

        script_content = f"""#!/bin/sh
cd {quoted_cwd}
echo "=== [roostr] Starting {job.name} ==="
{job.command}
echo ""
echo "=== [roostr] Job finished ==="
{tail_clause}"""
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IRUSR)
        return script_path

    def _resolve_terminal_command(self, preferred_app: TerminalApp) -> tuple[str, list[str]] | None:
        if preferred_app != TerminalApp.AUTO:
            app_name = preferred_app.value.lower()
            binary = self._which(app_name)
            if binary:
                flags = TERMINAL_SPECS.get(app_name, ["-e"])
                return binary, flags

        # In auto mode, iterate through known terminals
        for term, flags in TERMINAL_SPECS.items():
            binary = self._which(term)
            if binary:
                return binary, flags

        return None

    def launch(self, job: Job, dt: datetime) -> tuple[bool, str]:
        try:
            script_path = self.generate_runner_script(job)
            app = job.target.app if isinstance(job.target, TerminalTargetConfig) else TerminalApp.AUTO

            resolved = self._resolve_terminal_command(app)
            if not resolved:
                return (
                    False,
                    "No supported terminal emulator found (tried ghostty, kitty, alacritty, gnome-terminal, x-terminal-emulator, konsole, xterm)",
                )

            term_binary, flags = resolved
            cmd = [term_binary, *flags, str(script_path)]

            # Dispatch in background session so terminal outlives Roostr process
            self._cmd_runner(cmd, start_new_session=True, check=False)
            term_name = Path(term_binary).name
            return True, f"Launched in {term_name} terminal window ({script_path.name})"
        except Exception as e:
            return False, f"Error launching Linux terminal target: {e}"
