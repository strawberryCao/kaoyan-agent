from typing import Any, Optional

from kaoyan_agent.repositories.fortune_repository import FortuneRepository
from kaoyan_agent.repositories.mistake_review_repository import MistakeReviewRepository
from kaoyan_agent.repositories.nightly_review_repository import NightlyReviewRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.score_repository import ScoreRepository
from kaoyan_agent.repositories.study_task_repository import StudyTaskRepository


class WorkspaceWorkflow:
    """Aggregate data for the single kaoyan preparation workspace."""

    workflow_name = "workspace"

    def __init__(
        self,
        task_repository: StudyTaskRepository | None = None,
        problem_repository: ProblemRepository | None = None,
        score_repository: ScoreRepository | None = None,
        nightly_repository: NightlyReviewRepository | None = None,
        mistake_repository: MistakeReviewRepository | None = None,
        fortune_repository: FortuneRepository | None = None,
    ):
        self.task_repository = task_repository or StudyTaskRepository()
        self.problem_repository = problem_repository or ProblemRepository()
        self.score_repository = score_repository or ScoreRepository()
        self.nightly_repository = nightly_repository or NightlyReviewRepository()
        self.mistake_repository = mistake_repository or MistakeReviewRepository()
        self.fortune_repository = fortune_repository or FortuneRepository()

    def list_tasks(
        self,
        today: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.task_repository.list(date_str=today, limit=limit)

    def update_task_status(self, task_id: int, status: str) -> bool:
        return self.task_repository.update_status(task_id, status)

    def list_mistake_cards(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.mistake_repository.list_cards(limit=limit)

    def update_mistake_status(self, card_id: int, mastery_status: str) -> bool:
        return self.mistake_repository.update_mastery_status(card_id, mastery_status)

    def mistake_reason_counts(self) -> list[dict[str, Any]]:
        return self.mistake_repository.reason_counts()

    def list_score_records(
        self,
        subject: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self.score_repository.list_records(subject=subject, limit=limit)

    def list_latest_reviews(self, limit: int = 5) -> list[dict[str, Any]]:
        return self.nightly_repository.list_latest(limit=limit)

    def list_open_problems(self) -> list[dict[str, Any]]:
        return self.problem_repository.list_open()

    def update_problem_status(self, problem_id: int, status: str) -> bool:
        return self.problem_repository.update_status(problem_id, status)

    def list_fortune_items(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.fortune_repository.list_items(limit=limit)
