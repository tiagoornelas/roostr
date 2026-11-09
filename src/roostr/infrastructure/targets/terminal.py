import stat
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.enums import TerminalApp
from roostr.domain.models import Job, TerminalTargetConfig

DEFAULT_RUNNERS_DIR = Path.home() / ".local" / "state" / "roostr" / "runners"


class TerminalTargetAdapter(ExecutionTargetPort):
    def __init__(
        self,
        runners_dir: Path = DEFAULT_RUNNERS_DIR,
        cmd_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ):
        self.runners_dir = runners_dir
        self.runners_dir.mkdir(parents=True, exist_ok=True)
        self._cmd_runner = cmd_runner or subprocess.run

    def generate_runner_script(self, job: Job) -> Path:
        script_path = self.runners_dir / f"{job.id}.command"
        keep_open = isinstance(job.target, TerminalTargetConfig) and job.target.keep_open
        tail_clause = "exec zsh\n" if keep_open else ""

        script_content = f"""#!/bin/zsh -lic
cd {job.cwd}
echo "=== [roostr] Starting {job.name} ==="
{job.command}
echo ""
echo "=== [roostr] Job finished ==="
{tail_clause}"""
        script_path.write_text(script_content, encoding="utf-8")
        # Ensure executable permission chmod +x
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IRUSR)
        return script_path

    def launch(self, job: Job, dt: datetime) -> tuple[bool, str]:
        try:
            script_path = self.generate_runner_script(job)
            app = job.target.app if isinstance(job.target, TerminalTargetConfig) else TerminalApp.AUTO

            # Dispatch via AppleScript safely by passing script path as argv
            if app == TerminalApp.ITERM2:
                apple_script = """
                on run argv
                    set scriptPath to item 1 of argv
                    tell application "iTerm"
                        activate
                        create window with default profile command scriptPath
                    end tell
                end run
                """
            elif app == TerminalApp.GHOSTTY:
                # Ghostty can open a file via open -a Ghostty or AppleScript
                apple_script = """
                on run argv
                    set scriptPath to item 1 of argv
                    do shell script "open -a Ghostty " & quoted form of scriptPath
                end run
                """
            else:
                # Default Terminal.app
                apple_script = """
                on run argv
                    set scriptPath to item 1 of argv
                    tell application "Terminal"
                        activate
                        do script scriptPath
                    end tell
                end run
                """

            res = self._cmd_runner(
                ["osascript", "-e", apple_script, str(script_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if res.returncode != 0:
                return False, f"Failed to launch terminal window: {res.stderr.strip()}"

            return True, f"Launched in {app.value} terminal window ({script_path.name})"
        except Exception as e:
            return False, f"Error launching terminal target: {e}"
