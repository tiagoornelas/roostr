import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from roostr.application.ports import DaemonServicePort

DEFAULT_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"


class SystemdUserServiceAdapter(DaemonServicePort):
    """Linux user daemon service adapter using systemd (`systemctl --user`)."""

    def __init__(
        self,
        unit_dir: Path = DEFAULT_SYSTEMD_USER_DIR,
        binary_path: Path | None = None,
        cmd_runner: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    ):
        self.unit_dir = unit_dir
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

    @property
    def service_name(self) -> str:
        return "roostr.service"

    @property
    def unit_path(self) -> Path:
        return self.unit_dir / self.service_name

    def generate_service_unit(self) -> str:
        env_path = os.environ.get(
            "PATH",
            f"{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin",
        )
        if str(Path.home() / ".local/bin") not in env_path:
            env_path = f"{Path.home()}/.local/bin:{env_path}"

        return f"""[Unit]
Description=Roostr AI Task Runner Daemon
Documentation=https://github.com/tiagoornelas/roostr
After=network.target

[Service]
Type=simple
ExecStart={self._binary_path} daemon run
Restart=always
RestartSec=10
Environment="PATH={env_path}"

[Install]
WantedBy=default.target
"""

    def install(self) -> Path:
        self.unit_dir.mkdir(parents=True, exist_ok=True)
        unit_content = self.generate_service_unit()
        self.unit_path.write_text(unit_content, encoding="utf-8")

        self._cmd_runner(["systemctl", "--user", "daemon-reload"])
        self._cmd_runner(["systemctl", "--user", "enable", "--now", self.service_name])
        return self.unit_path

    def uninstall(self) -> None:
        try:
            self._cmd_runner(["systemctl", "--user", "stop", self.service_name])
        except Exception:
            pass
        try:
            self._cmd_runner(["systemctl", "--user", "disable", self.service_name])
        except Exception:
            pass

        if self.unit_path.exists():
            self.unit_path.unlink(missing_ok=True)

        try:
            self._cmd_runner(["systemctl", "--user", "daemon-reload"])
        except Exception:
            pass

    def start(self) -> None:
        self._cmd_runner(["systemctl", "--user", "start", self.service_name])

    def stop(self) -> None:
        self._cmd_runner(["systemctl", "--user", "stop", self.service_name])

    def is_running(self) -> bool:
        try:
            res = self._cmd_runner(["systemctl", "--user", "is-active", self.service_name])
            return res.returncode == 0 and res.stdout.strip() == "active"
        except Exception:
            return False
