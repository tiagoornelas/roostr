from datetime import datetime

from roostr.application.ports import JobRepositoryPort, NotificationPort
from roostr.domain.enums import ExecutionStatus, ScheduleFrequency, TriggerType
from roostr.domain.models import ExecutionRecord
from roostr.infrastructure.notifier import MacNotifierAdapter
from roostr.infrastructure.targets.dispatcher import TargetDispatcher


class ExecuteJobUseCase:
    def __init__(
        self,
        storage: JobRepositoryPort,
        dispatcher: TargetDispatcher | None = None,
        notifier: NotificationPort | None = None,
    ):
        self.storage = storage
        self.dispatcher = dispatcher or TargetDispatcher()
        self.notifier = notifier or MacNotifierAdapter()

    def execute(
        self,
        job_id: str,
        now: datetime | None = None,
        force: bool = False,
    ) -> tuple[ExecutionStatus, str]:
        current_dt = now or datetime.now()
        trigger = TriggerType.MANUAL if force else TriggerType.SCHEDULED

        job = self.storage.get_job(job_id)
        if not job:
            return ExecutionStatus.FAILED, f"Job '{job_id}' not found"

        if not force:
            if job.is_paused:
                return ExecutionStatus.SKIPPED_ALREADY_RAN, f"Job '{job.name}' is currently paused"

            # 1. Weekday check
            if not job.schedule.is_active_on_weekday(current_dt.weekday()):
                return (
                    ExecutionStatus.SKIPPED_OUTSIDE_WINDOW,
                    f"Outside of active days (current weekday: {current_dt.weekday()})",
                )

            # 2. Tolerance window check
            if not job.schedule.is_within_window(current_dt):
                return (
                    ExecutionStatus.SKIPPED_OUTSIDE_WINDOW,
                    f"Outside of scheduled window ({current_dt.strftime('%H:%M')})",
                )

            # 3. Idempotency check via SQLite
            if job.schedule.frequency == ScheduleFrequency.DAILY:
                if self.storage.has_succeeded_on_date(job_id, current_dt.date()):
                    return ExecutionStatus.SKIPPED_ALREADY_RAN, "Already executed successfully today"
            else:
                last_exec = self.storage.get_last_execution(job_id)
                if last_exec and last_exec.status == ExecutionStatus.SUCCESS:
                    if job.schedule.frequency == ScheduleFrequency.INTERVAL_MINUTES:
                        threshold_seconds = job.schedule.interval_value * 60
                    else:
                        threshold_seconds = job.schedule.interval_value * 3600
                    elapsed = (current_dt - last_exec.timestamp).total_seconds()
                    # 30-second leeway for scheduling drift
                    if elapsed < (threshold_seconds - 30):
                        return (
                            ExecutionStatus.SKIPPED_ALREADY_RAN,
                            f"Already ran recently ({int(elapsed // 60)}m ago, interval is {job.schedule.interval_value})",
                        )

        # 4. Dispatch via target dispatcher
        success, message = self.dispatcher.dispatch(job, current_dt)
        status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED

        record = ExecutionRecord(
            id=None,
            job_id=job.id,
            timestamp=current_dt,
            trigger_type=trigger,
            status=status,
            details=message,
        )
        self.storage.record_execution(record)

        if not success:
            self.notifier.notify(
                title=f"Roostr — {job.name}",
                message=f"Execution failed: {message}",
            )

        return status, message
