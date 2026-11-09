import subprocess
from collections.abc import Callable

from roostr.application.ports import NotificationPort


class MacNotifierAdapter(NotificationPort):
    def __init__(
        self,
        cmd_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    ):
        self._cmd_runner = cmd_runner or subprocess.run

    def notify(self, title: str, message: str) -> None:
        escaped_title = title.replace('"', '\\"')
        escaped_msg = message.replace('"', '\\"')
        script = f'display notification "{escaped_msg}" with title "{escaped_title}"'
        try:
            self._cmd_runner(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            pass
