from typing import List

from repositories.task_repository import TaskRepository
from schemas.task import DailyTaskCreate, DailyTaskRecord


class DailyTaskWorkflow:
    def __init__(self, task_repository: TaskRepository | None = None) -> None:
        self.task_repository = task_repository or TaskRepository()

    def get_today_tasks(self, seed_demo: bool = True) -> List[DailyTaskRecord]:
        if seed_demo:
            self.task_repository.seed_demo_tasks_if_empty()
        return self.task_repository.list_today_tasks()

    def add_task(self, payload: DailyTaskCreate) -> DailyTaskRecord:
        return self.task_repository.create_task(payload)
