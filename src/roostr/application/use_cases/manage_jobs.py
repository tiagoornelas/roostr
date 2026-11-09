from roostr.application.ports import JobRepositoryPort, SchedulerPort
from roostr.domain.models import Job


class ManageJobsUseCase:
    def __init__(
        self,
        storage: JobRepositoryPort,
        scheduler: SchedulerPort | None = None,
    ):
        self.storage = storage
        self.scheduler = scheduler

    def create_job(self, job: Job) -> None:
        self.storage.save_job(job)
        if self.scheduler and not job.is_paused:
            self.scheduler.install(job)

    def toggle_pause(self, job_id: str) -> bool:
        job = self.storage.get_job(job_id)
        if not job:
            return False

        new_paused_state = not job.is_paused
        self.storage.set_paused(job_id, new_paused_state)
        job.is_paused = new_paused_state

        if self.scheduler:
            if new_paused_state:
                self.scheduler.pause(job_id)
            else:
                self.scheduler.resume(job)
        return new_paused_state

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
