import asyncio
import logging
import signal
from datetime import datetime, time, timedelta
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
            if len(job.schedule.times_of_day) <= 1:
                if self.storage.has_succeeded_on_date(job.id, now.date()):
                    return False
                return True
            active_slot = job.schedule.get_active_time_slot(now)
            if not active_slot:
                return False
            recent = self.storage.get_recent_executions(job.id, limit=20)
            already_ran = any(
                rec.status == ExecutionStatus.SUCCESS
                and rec.timestamp.date() == now.date()
                and job.schedule.is_time_within_slot_window(active_slot, rec.timestamp)
                for rec in recent
            )
            return not already_ran
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


def calculate_next_job_run(job: Job, now: datetime, storage: JobRepositoryPort) -> datetime | None:
    if job.is_paused:
        return None

    sched = job.schedule
    if not sched.days_of_week:
        return None

    if sched.frequency == ScheduleFrequency.DAILY:
        times = sorted(sched.times_of_day)
        # 1. Check today if active
        if sched.is_active_on_weekday(now.weekday()):
            for t in times:
                if len(times) <= 1:
                    already_ran = storage.has_succeeded_on_date(job.id, now.date())
                else:
                    recent = storage.get_recent_executions(job.id, limit=20)
                    already_ran = any(
                        rec.status == ExecutionStatus.SUCCESS
                        and rec.timestamp.date() == now.date()
                        and sched.is_time_within_slot_window(t, rec.timestamp)
                        for rec in recent
                    )
                if already_ran:
                    continue

                # Not succeeded yet: is now within tolerance window?
                if sched.is_time_within_slot_window(t, now):
                    sec_to_next = 60 - now.second
                    if sec_to_next <= 0:
                        sec_to_next = 60
                    return now + timedelta(seconds=sec_to_next + 2)

                slot_dt = datetime.combine(now.date(), t)
                if now.time() < t:
                    return slot_dt + timedelta(seconds=2)

        # 2. Today has no remaining slots or is not an active day; find next active weekday
        for offset in range(1, 8):
            next_day = (now.weekday() + offset) % 7
            if sched.is_active_on_weekday(next_day):
                target_date = now.date() + timedelta(days=offset)
                return datetime.combine(target_date, times[0]) + timedelta(seconds=2)

        return None

    # Interval frequency
    step_seconds = (
        sched.interval_value * 60
        if sched.frequency == ScheduleFrequency.INTERVAL_MINUTES
        else sched.interval_value * 3600
    )
    last_exec = storage.get_last_execution(job.id)
    if last_exec and last_exec.status == ExecutionStatus.SUCCESS:
        candidate = last_exec.timestamp + timedelta(seconds=step_seconds)
    else:
        candidate = now

    if candidate < now:
        candidate = now

    # Ensure candidate is on an active day
    for offset in range(0, 8):
        day_candidate = (candidate.weekday() + offset) % 7
        if sched.is_active_on_weekday(day_candidate):
            if offset > 0:
                candidate = datetime.combine(
                    candidate.date() + timedelta(days=offset),
                    sched.start_time or time(0, 0),
                )
            break

    if sched.start_time and candidate.time() < sched.start_time:
        candidate = datetime.combine(candidate.date(), sched.start_time)
    elif sched.end_time and candidate.time() > sched.end_time:
        for offset in range(1, 8):
            next_day = (candidate.weekday() + offset) % 7
            if sched.is_active_on_weekday(next_day):
                candidate = datetime.combine(
                    candidate.date() + timedelta(days=offset),
                    sched.start_time or time(0, 0),
                )
                break

    if candidate <= now:
        sec_to_next = 60 - now.second
        if sec_to_next <= 0:
            sec_to_next = 60
        return now + timedelta(seconds=sec_to_next + 2)

    return candidate + timedelta(seconds=2)


def calculate_next_schedule_event(
    jobs: list[Job],
    now: datetime,
    storage: JobRepositoryPort,
) -> datetime:
    midnight = datetime.combine(now.date() + timedelta(days=1), time(0, 0, 2))
    candidates: list[datetime] = [midnight]

    for job in jobs:
        next_run = calculate_next_job_run(job, now, storage)
        if next_run and next_run > now:
            candidates.append(next_run)

    return min(candidates)
