import asyncio
import logging
import signal
from datetime import datetime
from typing import Any

from roostr.application.ports import JobRepositoryPort
from roostr.application.use_cases.execute_job import ExecuteJobUseCase
from roostr.domain.enums import ExecutionStatus, ScheduleFrequency
from roostr.domain.models import Job

logger = logging.getLogger("roostr.daemon")


class DaemonSchedulerUseCase:
    def __init__(
        self,
        storage: JobRepositoryPort,
        execute_job_use_case: ExecuteJobUseCase,
    ):
        self.storage = storage
        self.execute_job_use_case = execute_job_use_case
        self._running = False

    def is_job_due(self, job: Job, now: datetime) -> bool:
        if job.is_paused:
            return False

        # 1. Weekday check
        if not job.schedule.is_active_on_weekday(now.weekday()):
            return False

        # 2. Tolerance window check
        if not job.schedule.is_within_window(now):
            return False

        # 3. Frequency & idempotency checks
        if job.schedule.frequency == ScheduleFrequency.DAILY:
            if self.storage.has_succeeded_on_date(job.id, now.date()):
                return False
            return True
        else:
            last_exec = self.storage.get_last_execution(job.id)
            if not last_exec or last_exec.status != ExecutionStatus.SUCCESS:
                return True

            if job.schedule.frequency == ScheduleFrequency.INTERVAL_MINUTES:
                threshold_seconds = job.schedule.interval_value * 60
            else:
                threshold_seconds = job.schedule.interval_value * 3600

            elapsed = (now - last_exec.timestamp).total_seconds()
            return elapsed >= (threshold_seconds - 30)

    def tick(self, now: datetime | None = None) -> list[tuple[str, ExecutionStatus, str]]:
        current_dt = now or datetime.now()
        results: list[tuple[str, ExecutionStatus, str]] = []

        jobs = self.storage.list_jobs()
        for job in jobs:
            if self.is_job_due(job, current_dt):
                status, msg = self.execute_job_use_case.execute(
                    job.id,
                    now=current_dt,
                    force=False,
                )
                results.append((job.id, status, msg))

        return results

    async def run_forever_async(self, poll_interval_seconds: int = 60) -> None:
        self._running = True
        logger.info("Roostr daemon started")

        while self._running:
            now = datetime.now()
            try:
                self.tick(now)
            except Exception as e:
                logger.error(f"Error during daemon tick: {e}", exc_info=True)

            # Sleep until the start of next minute
            seconds_to_next_minute = 60 - datetime.now().second
            if seconds_to_next_minute <= 0:
                seconds_to_next_minute = 60

            sleep_time = min(poll_interval_seconds, seconds_to_next_minute)
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break

        logger.info("Roostr daemon stopped")

    def run_forever(self, poll_interval_seconds: int = 60) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def _handle_signal(*args: Any) -> None:
            self._running = False
            for task in asyncio.all_tasks(loop):
                task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handle_signal)
            except Exception:
                pass

        try:
            loop.run_until_complete(self.run_forever_async(poll_interval_seconds))
        finally:
            loop.close()
