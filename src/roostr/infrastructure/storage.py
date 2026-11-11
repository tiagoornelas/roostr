import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path

from roostr.domain.enums import (
    ActionType,
    AIHarness,
    ExecutionStatus,
    ScheduleFrequency,
    TargetType,
    TerminalApp,
    ToleranceMode,
    TriggerType,
)
from roostr.domain.models import (
    AgentAction,
    BackgroundTargetConfig,
    CommandAction,
    ExecutionRecord,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TargetConfig,
    TerminalTargetConfig,
    parse_time_string,
    parse_times_list,
)


class SQLiteStorage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    command TEXT NOT NULL,
                    days_of_week TEXT NOT NULL,
                    time_of_day TEXT NOT NULL,
                    tolerance_mode TEXT NOT NULL,
                    tolerance_value INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_config TEXT NOT NULL,
                    is_paused INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    folder TEXT,
                    action_type TEXT NOT NULL DEFAULT 'command',
                    harness TEXT,
                    prompt TEXT,
                    frequency TEXT NOT NULL DEFAULT 'daily',
                    interval_value INTEGER NOT NULL DEFAULT 1,
                    start_time TEXT,
                    end_time TEXT
                );

                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS folders (
                    name TEXT PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_executions_job_date 
                ON executions(job_id, timestamp, status);
            """)

            cursor = conn.execute("PRAGMA table_info(jobs)")
            columns = [c[1] for c in cursor.fetchall()]
            if "folder" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN folder TEXT")
            if "action_type" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN action_type TEXT NOT NULL DEFAULT 'command'")
            if "harness" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN harness TEXT")
            if "prompt" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN prompt TEXT")
            if "frequency" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN frequency TEXT NOT NULL DEFAULT 'daily'")
            if "interval_value" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN interval_value INTEGER NOT NULL DEFAULT 1")
            if "start_time" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN start_time TEXT")
            if "end_time" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN end_time TEXT")

            conn.execute(
                """
                INSERT OR IGNORE INTO folders (name)
                SELECT DISTINCT folder FROM jobs WHERE folder IS NOT NULL AND folder != ''
                """
            )

    def save_job(self, job: Job) -> None:
        if job.folder:
            self.save_folder(job.folder)
        target_dict = self._target_to_dict(job.target)
        action_type = job.action.action_type.value
        harness = job.action.harness.value if isinstance(job.action, AgentAction) else None
        prompt = job.action.prompt if isinstance(job.action, AgentAction) else None
        frequency = job.schedule.frequency.value
        interval_value = job.schedule.interval_value
        times_str = ",".join(t.strftime("%H:%M") for t in job.schedule.times_of_day)
        start_time_str = job.schedule.start_time.strftime("%H:%M") if job.schedule.start_time else None
        end_time_str = job.schedule.end_time.strftime("%H:%M") if job.schedule.end_time else None

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, name, cwd, command, days_of_week, time_of_day,
                    tolerance_mode, tolerance_value, target_type, target_config,
                    is_paused, created_at, folder, action_type, harness, prompt,
                    frequency, interval_value, start_time, end_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    cwd = excluded.cwd,
                    command = excluded.command,
                    days_of_week = excluded.days_of_week,
                    time_of_day = excluded.time_of_day,
                    tolerance_mode = excluded.tolerance_mode,
                    tolerance_value = excluded.tolerance_value,
                    target_type = excluded.target_type,
                    target_config = excluded.target_config,
                    is_paused = excluded.is_paused,
                    folder = excluded.folder,
                    action_type = excluded.action_type,
                    harness = excluded.harness,
                    prompt = excluded.prompt,
                    frequency = excluded.frequency,
                    interval_value = excluded.interval_value,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time
                """,
                (
                    job.id,
                    job.name,
                    job.cwd,
                    job.command,
                    json.dumps(list(job.schedule.days_of_week)),
                    times_str,
                    job.schedule.tolerance_mode.value,
                    job.schedule.tolerance_value,
                    job.target.target_type.value,
                    json.dumps(target_dict),
                    1 if job.is_paused else 0,
                    job.created_at.isoformat(),
                    job.folder,
                    action_type,
                    harness,
                    prompt,
                    frequency,
                    interval_value,
                    start_time_str,
                    end_time_str,
                ),
            )

    def get_job(self, job_id: str) -> Job | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def list_jobs(self) -> list[Job]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY name ASC").fetchall()
            return [self._row_to_job(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def save_folder(self, name: str) -> str:
        cleaned = "/".join([p.strip() for p in name.strip().strip("/").split("/") if p.strip()])
        if not cleaned:
            raise ValueError("Folder name cannot be empty")
        parts = cleaned.split("/")
        if len(parts) > 2:
            raise ValueError(f"Folder hierarchy cannot exceed 2 levels (got '{name}')")

        with self._connection() as conn:
            if len(parts) == 2:
                conn.execute("INSERT OR IGNORE INTO folders (name) VALUES (?)", (parts[0],))
            conn.execute("INSERT OR IGNORE INTO folders (name) VALUES (?)", (cleaned,))
        return cleaned

    def list_folders(self) -> list[str]:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT name FROM folders
                UNION
                SELECT DISTINCT folder FROM jobs WHERE folder IS NOT NULL AND folder != ''
                ORDER BY name ASC
                """
            )
            return [row[0] for row in cursor.fetchall() if row[0]]

    def delete_folder(self, name: str) -> None:
        cleaned = "/".join([p.strip() for p in name.strip().strip("/").split("/") if p.strip()])
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE folder = ? OR folder LIKE ? || '/%'",
                (cleaned, cleaned),
            )
            count = cursor.fetchone()[0]
            if count > 0:
                raise ValueError(f"Cannot delete folder '{cleaned}': contains {count} job(s)")
            conn.execute("DELETE FROM folders WHERE name = ? OR name LIKE ? || '/%'", (cleaned, cleaned))

    def move_job(self, job_id: str, folder: str | None) -> None:
        cleaned_folder: str | None = None
        if folder:
            cleaned_folder = self.save_folder(folder)
        with self._connection() as conn:
            conn.execute("UPDATE jobs SET folder = ? WHERE id = ?", (cleaned_folder, job_id))

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connection() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def set_paused(self, job_id: str, paused: bool) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE jobs SET is_paused = ? WHERE id = ?",
                (1 if paused else 0, job_id),
            )

    def record_execution(self, record: ExecutionRecord) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO executions (job_id, timestamp, trigger_type, status, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.job_id,
                    record.timestamp.isoformat(),
                    record.trigger_type.value,
                    record.status.value,
                    record.details,
                ),
            )

    def count_executions(self, job_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM executions WHERE job_id = ?", (job_id,)).fetchone()
            return int(row[0]) if row else 0

    def get_last_execution(self, job_id: str) -> ExecutionRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM executions 
                WHERE job_id = ? 
                ORDER BY timestamp DESC LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if not row:
                return None
            return ExecutionRecord(
                id=row["id"],
                job_id=row["job_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                trigger_type=TriggerType(row["trigger_type"]),
                status=ExecutionStatus(row["status"]),
                details=row["details"],
            )

    def get_recent_executions(self, job_id: str | None = None, limit: int = 5) -> list[ExecutionRecord]:
        with self._connection() as conn:
            if job_id:
                rows = conn.execute(
                    """
                    SELECT * FROM executions 
                    WHERE job_id = ? 
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (job_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM executions 
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [
                ExecutionRecord(
                    id=row["id"],
                    job_id=row["job_id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    trigger_type=TriggerType(row["trigger_type"]),
                    status=ExecutionStatus(row["status"]),
                    details=row["details"],
                )
                for row in rows
            ]

    def has_succeeded_on_date(self, job_id: str, target_date: date) -> bool:
        start_ts = datetime.combine(target_date, time.min).isoformat()
        end_ts = datetime.combine(target_date, time.max).isoformat()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM executions
                WHERE job_id = ?
                  AND status = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                """,
                (job_id, ExecutionStatus.SUCCESS.value, start_ts, end_ts),
            ).fetchone()
            return bool(row and row[0] > 0)

    def _target_to_dict(self, target: TargetConfig) -> dict:
        if isinstance(target, TerminalTargetConfig):
            return {"app": target.app.value, "keep_open": target.keep_open}
        if isinstance(target, HerdrTargetConfig):
            return {
                "space": target.space,
                "tab_template": target.tab_template,
                "keep_open": target.keep_open,
            }
        if isinstance(target, BackgroundTargetConfig):
            return {"notify_on_complete": target.notify_on_complete}
        return {}

    def _dict_to_target(self, target_type_str: str, config_dict: dict) -> TargetConfig:
        target_type = TargetType(target_type_str)
        if target_type == TargetType.TERMINAL:
            return TerminalTargetConfig(
                app=TerminalApp(config_dict.get("app", "auto")),
                keep_open=bool(config_dict.get("keep_open", True)),
            )
        if target_type == TargetType.HERDR:
            return HerdrTargetConfig(
                space=config_dict.get("space", ""),
                tab_template=config_dict.get("tab_template", "{job.name} {DD}/{MM}"),
                keep_open=bool(config_dict.get("keep_open", True)),
            )
        if target_type == TargetType.BACKGROUND:
            return BackgroundTargetConfig(
                notify_on_complete=bool(config_dict.get("notify_on_complete", True)),
            )
        return TerminalTargetConfig()

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        times_of_day = parse_times_list(row["time_of_day"])
        time_of_day = times_of_day[0] if times_of_day else time(8, 0)
        freq_raw = row["frequency"] if "frequency" in row.keys() and row["frequency"] else "daily"
        interval_val = (
            row["interval_value"] if "interval_value" in row.keys() and row["interval_value"] is not None else 1
        )
        start_time = parse_time_string(row["start_time"]) if "start_time" in row.keys() and row["start_time"] else None
        end_time = parse_time_string(row["end_time"]) if "end_time" in row.keys() and row["end_time"] else None
        schedule = SchedulePolicy(
            days_of_week=tuple(json.loads(row["days_of_week"])),
            time_of_day=time_of_day,
            times_of_day=times_of_day,
            start_time=start_time,
            end_time=end_time,
            tolerance_mode=ToleranceMode(row["tolerance_mode"]),
            tolerance_value=row["tolerance_value"],
            frequency=ScheduleFrequency(freq_raw),
            interval_value=int(interval_val),
        )
        target = self._dict_to_target(row["target_type"], json.loads(row["target_config"]))
        folder = row["folder"] if "folder" in row.keys() and row["folder"] else None

        action_type_raw = row["action_type"] if "action_type" in row.keys() and row["action_type"] else "command"
        harness_raw = row["harness"] if "harness" in row.keys() and row["harness"] else None
        prompt_raw = row["prompt"] if "prompt" in row.keys() and row["prompt"] else ""

        if action_type_raw == ActionType.AGENT.value and harness_raw:
            action = AgentAction(harness=AIHarness(harness_raw), prompt=prompt_raw)
        else:
            action = CommandAction(command=row["command"])

        return Job(
            id=row["id"],
            name=row["name"],
            cwd=row["cwd"],
            schedule=schedule,
            target=target,
            action=action,
            is_paused=bool(row["is_paused"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            folder=folder,
        )
