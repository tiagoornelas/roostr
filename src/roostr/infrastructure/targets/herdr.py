import json
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.models import AgentAction, HerdrTargetConfig, Job

ROOSTR_SVG_ICON = """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="em1-crest" x1="6" y1="1.5" x2="17" y2="10" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FB7185"/>
      <stop offset="50%" stop-color="#EF4444"/>
      <stop offset="100%" stop-color="#B91C1C"/>
    </linearGradient>
    <linearGradient id="em1-wattle" x1="14" y1="13" x2="18" y2="19.5" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#F87171"/>
      <stop offset="100%" stop-color="#991B1B"/>
    </linearGradient>
    <linearGradient id="em1-body" x1="5" y1="6" x2="16" y2="22" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="45%" stop-color="#F5EBE1"/>
      <stop offset="80%" stop-color="#C89F78"/>
      <stop offset="100%" stop-color="#7C4D2B"/>
    </linearGradient>
    <linearGradient id="em1-beak" x1="17" y1="8.5" x2="23" y2="12.5" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FEF08A"/>
      <stop offset="40%" stop-color="#FACC15"/>
      <stop offset="100%" stop-color="#EA580C"/>
    </linearGradient>
  </defs>
  <path d="M16.5 8.5L22.2 10.6C22.7 10.8 22.7 11.5 22.2 11.7L16.5 13.8V8.5Z" fill="url(#em1-beak)"/>
  <path d="M15.8 12.8C18.2 13.8 19.2 16.5 17.8 18.4C16.6 20 14.2 19.6 13.5 17.5C13 15.8 14.2 13.5 15.8 12.8Z" fill="url(#em1-wattle)"/>
  <path d="M7.5 8.5C4.8 11.2 4.2 16.2 6.8 19.8C8.8 22.4 13.2 22.5 16.2 21.2C13.5 19.8 12.8 16.8 14.2 14.2C15.2 12.4 17.5 11.8 17.5 9.8C17.5 7.8 15 6.8 12 7C9.8 7.1 8.5 7.5 7.5 8.5Z" fill="url(#em1-body)"/>
  <path d="M7.2 9.2C5.2 7.5 5.4 4.2 7.8 3.8C8.4 3.7 9 4 9.4 4.4C9.8 2.2 12.4 1.2 14.1 2.8C14.5 3.2 14.7 3.7 14.8 4.2C16.5 3.2 18.8 4.5 18.4 6.6C18.1 8.2 16.4 9.2 14.4 9.2C11.8 9.2 9.2 9.6 7.2 9.2Z" fill="url(#em1-crest)"/>
  <circle cx="13.2" cy="9.6" r="1.45" fill="#1E140C"/>
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
            "tint": False,
            "tile": "#1c1d21",
            "color": "#ffffff",
            "match": ["roostr"],
        }

        programs_file.write_text(json.dumps(programs_data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def make_herdr_terminal_name(job_id: str, dt: datetime) -> str:
    """Generate a valid Herdr terminal name adhering to schema:
    1-32 chars of a-z, 0-9, -, _, . starting with a letter or digit, not shaped like an id (t\\d+).
    """
    ts = dt.strftime("%Y%m%d-%H%M%S")  # 15 chars
    clean_id = re.sub(r"[^a-z0-9_-]", "", job_id.lower())
    max_prefix_len = 32 - len(ts) - 1  # 16 chars
    prefix = clean_id[:max_prefix_len].rstrip("-_.")
    if not prefix or not prefix[0].isalnum():
        prefix = "j"
    return f"{prefix}-{ts}"[:32]


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

    def _list_spaces(self) -> tuple[list[dict] | None, str | None]:
        try:
            res = self._cmd_runner(
                ["herdr-app", "ls"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode != 0:
                detail = res.stderr.strip() or res.stdout.strip() or f"exit code {res.returncode}"
                return None, f"Failed to list Herdr spaces: {detail}"
            if not res.stdout.strip():
                return None, "Failed to list Herdr spaces: empty output"
            data = json.loads(res.stdout)
            spaces = data.get("spaces", [])
            if not isinstance(spaces, list):
                return None, "Failed to list Herdr spaces: invalid response shape"
            return spaces, None
        except subprocess.TimeoutExpired:
            return None, "Timed out listing Herdr spaces"
        except Exception as e:
            return None, f"Error listing Herdr spaces: {e}"

    def get_space_id(self, space_name: str) -> str | None:
        spaces, _ = self._list_spaces()
        if not spaces:
            return None
        for space in spaces:
            if space.get("name") == space_name:
                return space.get("id")
        return None

    def get_or_create_space_id(self, space_name: str, cwd: str) -> tuple[str | None, str | None]:
        clean_name = space_name.strip() if space_name else "Roostr"
        space_id = self.get_space_id(clean_name)
        if space_id:
            return space_id, None

        try:
            res = self._cmd_runner(
                ["herdr-app", "do", "space.new", "--name", clean_name, "--folder", cwd],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            new_id = self.get_space_id(clean_name)
            if new_id:
                return new_id, None
            return None, f"Failed to create space '{clean_name}': {res.stderr.strip()}"
        except Exception as e:
            return None, f"Error calling herdr-app to create space: {e}"

    def _find_matching_tab(self, spaces: list[dict], space_name: str, tab_label: str) -> tuple[str | None, dict | None]:
        for space in spaces:
            if space.get("name") == space_name:
                space_id = space.get("id")
                for tab in space.get("tabs", []):
                    if tab.get("name") == tab_label:
                        return space_id, tab
                return space_id, None
        return None, None

    def _send_to_existing_tab(self, job: Job, tab: dict, tab_label: str) -> tuple[bool, str]:
        tab_id = tab.get("id") or "unknown"
        terminals = tab.get("terminals") or []
        if not terminals:
            return False, f"Matching tab {tab_id} ('{tab_label}') has no terminals"

        first_term = terminals[0]
        term_id = first_term.get("terminal") or first_term.get("name")
        if not term_id:
            return False, f"Matching tab {tab_id} ('{tab_label}') has no usable terminal"

        # Check live terminal status via hc get: finished agent turns report "done",
        # which `hc send --if idle` rejects, while plain shells have no status.
        try:
            get_res = self._cmd_runner(
                ["hc", "get", "--json", term_id],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f"Timed out checking terminal {term_id} status"
        except Exception as e:
            return False, f"Error checking terminal {term_id} status: {e}"

        get_data: dict = {}
        if get_res.stdout and get_res.stdout.strip():
            try:
                parsed = json.loads(get_res.stdout)
                if isinstance(parsed, dict):
                    get_data = parsed
            except Exception:
                pass

        if get_res.returncode != 0 or "error" in get_data:
            err_obj = get_data.get("error") if isinstance(get_data.get("error"), dict) else {}
            reason = (
                err_obj.get("message")
                or get_res.stderr.strip()
                or get_res.stdout.strip()
                or f"exit {get_res.returncode}"
            )
            return False, f"Cannot send to terminal {term_id}: {reason}"

        if get_data.get("state") != "live":
            return False, f"Terminal {term_id} is not live (state: {get_data.get('state')})"

        status_obj = get_data.get("status")
        state_val = status_obj.get("state") if isinstance(status_obj, dict) else None
        if not state_val:
            return False, f"Terminal {term_id} has no active agent status"
        if state_val not in ("idle", "done"):
            kind = status_obj.get("kind") if isinstance(status_obj, dict) else None
            detail = f"{state_val} ({kind})" if kind else state_val
            return False, f"Terminal {term_id} is not ready (status: {detail})"

        text = job.action.prompt if isinstance(job.action, AgentAction) else job.command
        send_cmd = ["hc", "send", "--json"]
        if state_val == "idle":
            send_cmd.extend(["--if", "idle"])
        send_cmd.extend(["--", term_id, text])

        try:
            send_res = self._cmd_runner(
                send_cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return (
                False,
                f"Timed out waiting to send to terminal {term_id} (user may be typing a draft or hc is unresponsive)",
            )
        except Exception as e:
            return False, f"Error calling hc send on terminal {term_id}: {e}"

        send_data: dict = {}
        if send_res.stdout and send_res.stdout.strip():
            try:
                parsed = json.loads(send_res.stdout)
                if isinstance(parsed, dict):
                    send_data = parsed
            except Exception:
                pass

        if send_res.returncode != 0 or "error" in send_data:
            err_obj = send_data.get("error") if isinstance(send_data.get("error"), dict) else {}
            reason = (
                err_obj.get("message")
                or send_res.stderr.strip()
                or send_res.stdout.strip()
                or f"exit {send_res.returncode}"
            )
            return False, f"Failed to send to terminal {term_id}: {reason}"

        extra = f" (first of {len(terminals)} terminals)" if len(terminals) > 1 else ""
        return True, f"Sent to terminal {term_id} in tab {tab_id} ('{tab_label}'){extra}"

    def launch(self, job: Job, dt: datetime) -> tuple[bool, str]:
        if not self.is_running():
            return False, "Herdr is not running"

        if not isinstance(job.target, HerdrTargetConfig):
            return False, "Job target is not configured for Herdr"

        target_space = job.target.space.strip() if job.target.space else "Roostr"
        tab_label = job.resolve_herdr_tab_name(dt)

        space_id: str | None = None
        if job.target.reuse_open_tab:
            spaces, err = self._list_spaces()
            if err or spaces is None:
                return False, err or "Failed to list Herdr spaces"
            space_id, matching_tab = self._find_matching_tab(spaces, target_space, tab_label)
            if matching_tab is not None:
                return self._send_to_existing_tab(job, matching_tab, tab_label)

        if not space_id:
            space_id, err = self.get_or_create_space_id(target_space, job.cwd)
            if not space_id:
                return False, err or f'Space "{target_space}" could not be created in Herdr'

        terminal_name = make_herdr_terminal_name(job.id, dt)

        keep_open = getattr(job.target, "keep_open", True)
        if keep_open:
            cmd_args = [
                "env",
                "TERM=xterm-256color",
                "zsh",
                "-lic",
                'eval "$@"; exec "$0" -li',
                "zsh",
                job.command,
            ]
        else:
            cmd_args = [
                "env",
                "TERM=xterm-256color",
                "zsh",
                "-lic",
                job.command,
            ]

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
            *cmd_args,
        ]

        try:
            res = self._cmd_runner(hc_cmd, capture_output=True, text=True, timeout=10, check=False)
            if res.returncode != 0:
                return False, f"Failed to execute hc run: {res.stderr.strip()}"
        except Exception as e:
            return False, f"Error spawning hc process: {e}"

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
