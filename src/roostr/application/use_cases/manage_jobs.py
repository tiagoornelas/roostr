from roostr.application.ports import JobRepositoryPort, SchedulerPort
from roostr.domain.models import ExecutionRecord, Job


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

    def list_jobs(self, folder: str | None = None, is_paused: bool | None = None) -> list[Job]:
        jobs = self.storage.list_jobs()
        if folder is not None:
            clean_folder = folder.strip().strip("/")
            jobs = [
                j for j in jobs
                if j.folder == clean_folder or (j.folder and j.folder.startswith(f"{clean_folder}/"))
            ]
        if is_paused is not None:
            jobs = [j for j in jobs if j.is_paused == is_paused]
        return jobs

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

    def delete_folder(self, folder: str) -> None:
        self.storage.delete_folder(folder)

    def list_folders(self) -> list[str]:
        return self.storage.list_folders()

    def get_recent_executions(self, job_id: str | None = None, limit: int = 20) -> list[ExecutionRecord]:
        return self.storage.get_recent_executions(job_id, limit=limit)

