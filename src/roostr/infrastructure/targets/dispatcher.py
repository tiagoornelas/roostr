from datetime import datetime

from roostr.application.ports import ExecutionTargetPort
from roostr.domain.enums import TargetType
from roostr.domain.models import Job
from roostr.infrastructure.platform import get_default_terminal_target_adapter
from roostr.infrastructure.targets.background import BackgroundTargetAdapter
from roostr.infrastructure.targets.herdr import HerdrTargetAdapter


class TargetDispatcher:
    def __init__(
        self,
        terminal_adapter: ExecutionTargetPort | None = None,
        herdr_adapter: ExecutionTargetPort | None = None,
        background_adapter: ExecutionTargetPort | None = None,
    ):
        self.terminal_adapter = terminal_adapter or get_default_terminal_target_adapter()
        self.herdr_adapter = herdr_adapter or HerdrTargetAdapter()
        self.background_adapter = background_adapter or BackgroundTargetAdapter()

    def get_adapter(self, target_type: TargetType) -> ExecutionTargetPort:
        if target_type == TargetType.HERDR:
            return self.herdr_adapter
        if target_type == TargetType.BACKGROUND:
            return self.background_adapter
        return self.terminal_adapter

    def dispatch(self, job: Job, dt: datetime) -> tuple[bool, str]:
        adapter = self.get_adapter(job.target.target_type)
        return adapter.launch(job, dt)
