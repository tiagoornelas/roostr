from datetime import datetime

from roostr.application.ports import JobRepositoryPort, SchedulerPort
from roostr.domain.enums import ScheduleFrequency
from roostr.domain.models import ExecutionRecord, Job, SchedulePolicy, slugify


class ManageJobsUseCase:
    def __init__(
        self,
        storage: JobRepositoryPort,
        scheduler: SchedulerPort | None = None,
    ):
        self.storage = storage
        self.scheduler = scheduler

    def get_job(self, job_id: str) -> Job | None:
        return self.storage.get_job(job_id)

    def get_one_time_state(self, job: Job, executed_ids: set[str] | None = None) -> str:
        """Return 'executed', 'paused', or 'scheduled' for a one-time job."""
        has_ran = job.id in executed_ids if executed_ids is not None else self.storage.has_terminal_execution(job.id)
        if has_ran:
            return "executed"
        if job.is_paused:
            return "paused"
        return "scheduled"

    def list_jobs(
        self,
        folder: str | None = None,
        is_paused: bool | None = None,
        job_type: str | None = None,
        one_time_state: str | None = None,
    ) -> list[Job]:
        jobs = self.storage.list_jobs()
        if folder is not None:
            clean_folder = folder.strip().strip("/")
            jobs = [
                j for j in jobs if j.folder == clean_folder or (j.folder and j.folder.startswith(f"{clean_folder}/"))
            ]
        if is_paused is not None:
            jobs = [j for j in jobs if j.is_paused == is_paused]
        if job_type == "recurring":
            jobs = [j for j in jobs if j.schedule.frequency != ScheduleFrequency.ONCE]
        elif job_type == "once":
            jobs = [j for j in jobs if j.schedule.frequency == ScheduleFrequency.ONCE]

        if one_time_state in ("scheduled", "executed", "paused"):
            executed_ids = self.storage.get_executed_job_ids()
            jobs = [
                j
                for j in jobs
                if j.schedule.frequency == ScheduleFrequency.ONCE
                and self.get_one_time_state(j, executed_ids) == one_time_state
            ]
        return jobs

    def generate_unique_id(self, base_name: str) -> str:
        base_id = slugify(base_name)
        candidate = base_id
        counter = 1
        while self.storage.get_job(candidate) is not None:
            candidate = f"{base_id}-{counter}"
            counter += 1
        return candidate

    def clone_job(
        self,
        job_id: str,
        run_at: datetime | None = None,
        name: str | None = None,
    ) -> Job:
        source = self.storage.get_job(job_id)
        if not source:
            raise ValueError(f"Job '{job_id}' not found")

        new_name = name.strip() if name else source.name
        new_id = self.generate_unique_id(new_name)
        target_run_at = run_at if run_at is not None else source.schedule.run_at

        if source.schedule.frequency == ScheduleFrequency.ONCE or target_run_at is not None:
            if target_run_at is None:
                raise ValueError("run_at is required when cloning a one-time job")
            new_schedule = SchedulePolicy(
                frequency=ScheduleFrequency.ONCE,
                run_at=target_run_at,
                tolerance_mode=source.schedule.tolerance_mode,
                tolerance_value=source.schedule.tolerance_value,
            )
        else:
            new_schedule = SchedulePolicy(
                days_of_week=source.schedule.days_of_week,
                time_of_day=source.schedule.time_of_day,
                times_of_day=source.schedule.times_of_day,
                tolerance_mode=source.schedule.tolerance_mode,
                tolerance_value=source.schedule.tolerance_value,
                frequency=source.schedule.frequency,
                interval_value=source.schedule.interval_value,
                start_time=source.schedule.start_time,
                end_time=source.schedule.end_time,
            )

        cloned = Job(
            id=new_id,
            name=new_name,
            cwd=source.cwd,
            schedule=new_schedule,
            target=source.target,
            action=source.action,
            is_paused=False,
            created_at=datetime.now(),
            folder=source.folder,
        )
        self.create_job(cloned)
        return cloned

    def create_job(self, job: Job) -> None:
        self.storage.save_job(job)
        if self.scheduler and not job.is_paused:
            self.scheduler.install(job)

    def update_job(self, job: Job) -> None:
        self.storage.save_job(job)
        if self.scheduler:
            if job.is_paused:
                self.scheduler.pause(job.id)
            else:
                self.scheduler.install(job)

    def set_paused(self, job_id: str, paused: bool) -> bool:
        job = self.storage.get_job(job_id)
        if not job:
            return False

        self.storage.set_paused(job_id, paused)
        job.is_paused = paused

        if self.scheduler:
            if paused:
                self.scheduler.pause(job_id)
            else:
                self.scheduler.resume(job)
        return paused

    def toggle_pause(self, job_id: str) -> bool:
        job = self.storage.get_job(job_id)
        if not job:
            return False

        new_paused_state = not job.is_paused
        return self.set_paused(job_id, new_paused_state)

    def delete_job(self, job_id: str) -> None:
        if self.scheduler:
            self.scheduler.uninstall(job_id)
        self.storage.delete_job(job_id)

    def move_job(self, job_id: str, folder: str | None) -> None:
        self.storage.move_job(job_id, folder)

    def create_folder(self, folder: str) -> str:
        return self.storage.save_folder(folder)

    def rename_folder(self, old_name: str, new_name: str) -> str:
        return self.storage.rename_folder(old_name, new_name)

    def delete_folder(self, folder: str, force: bool = False, delete_jobs: bool = False) -> None:
        if delete_jobs and self.scheduler:
            jobs = self.list_jobs(folder=folder)
            for j in jobs:
                self.scheduler.uninstall(j.id)
        self.storage.delete_folder(folder, force=force, delete_jobs=delete_jobs)

    def list_folders(self) -> list[str]:
        return self.storage.list_folders()

    def get_recent_executions(self, job_id: str | None = None, limit: int = 20) -> list[ExecutionRecord]:
        return self.storage.get_recent_executions(job_id, limit=limit)
