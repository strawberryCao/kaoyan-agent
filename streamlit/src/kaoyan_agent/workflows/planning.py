from typing import Any, Dict, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.agents.motivation import MotivationAgent
from kaoyan_agent.agents.practice_review import PracticeReviewAgent
from kaoyan_agent.repositories.motivation import MotivationRepository
from kaoyan_agent.repositories.practice_review import PracticeReviewRepository
from kaoyan_agent.repositories.score import ScoreRepository
from kaoyan_agent.repositories.study_tasks import StudyTaskRepository


class PlanningWorkflow:
    workflow_name = "planning"

    def __init__(
        self,
        settings: Settings | None = None,
        project_id: Optional[int] = None,
        task_repository: StudyTaskRepository | None = None,
        score_repository: ScoreRepository | None = None,
        practice_repository: PracticeReviewRepository | None = None,
        motivation_repository: MotivationRepository | None = None,
    ):
        self.settings = settings or get_settings()
        self.project_id = project_id
        self.task_repository = task_repository or StudyTaskRepository()
        self.score_repository = score_repository or ScoreRepository()
        self.practice_repository = practice_repository or PracticeReviewRepository()
        self.motivation_repository = motivation_repository or MotivationRepository()
        self.practice_agent = PracticeReviewAgent(self.settings)
        self.motivation_agent = MotivationAgent(self.settings)

    def create_task_from_problem(
        self,
        problem: Dict[str, Any],
        scheduled_date: Optional[str] = None,
        estimated_minutes: int = 25,
        project_id: Optional[int] = None,
    ) -> int:
        title = (
            problem.get("suggested_action")
            or problem.get("description")
            or "Handle one open problem"
        )
        return self.task_repository.create(
            title=str(title),
            subject=str(problem.get("subject") or ""),
            estimated_minutes=estimated_minutes,
            source="Problem Board",
            related_problem_id=problem.get("id"),
            scheduled_date=scheduled_date,
            project_id=project_id if project_id is not None else self.project_id,
        )

    def create_task(
        self,
        title: str,
        subject: str = "",
        estimated_minutes: int = 0,
        source: str = "",
        status: str = "todo",
        related_problem_id: Optional[int] = None,
        scheduled_date: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> int:
        return self.task_repository.create(
            title=title,
            subject=subject,
            estimated_minutes=estimated_minutes,
            source=source,
            status=status,
            related_problem_id=related_problem_id,
            scheduled_date=scheduled_date,
            project_id=project_id if project_id is not None else self.project_id,
        )

    def record_score(
        self,
        subject: str,
        score: float,
        full_score: float,
        exam_type: str,
        exam_date: str,
        note: str = "",
        project_id: Optional[int] = None,
    ) -> int:
        return self.score_repository.create_record(
            subject=subject,
            score=score,
            full_score=full_score,
            exam_type=exam_type,
            exam_date=exam_date,
            note=note,
            project_id=project_id if project_id is not None else self.project_id,
        )

    def generate_and_save_practice_card(
        self,
        subject: str,
        chapter: str,
        question: str,
        user_reason: str = "",
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        card = self.practice_agent.generate_card(
            subject=subject,
            chapter=chapter,
            question=question,
            user_reason=user_reason,
        )
        card_id = self.practice_repository.create_card(
            subject=subject,
            chapter=chapter,
            question=question,
            analysis=card["analysis"],
            mistake_reason=card["mistake_reason"],
            knowledge_points=card["knowledge_points"],
            review_priority=card["review_priority"],
            project_id=project_id if project_id is not None else self.project_id,
        )
        return {**card, "id": card_id, "subject": subject, "chapter": chapter}

    def generate_daily_sign(self, project_id: Optional[int] = None) -> Dict[str, Any]:
        sign = self.motivation_agent.generate_daily_sign()
        item_id = self.motivation_repository.create_item(
            sign_type="daily_sign",
            sign_level=sign["sign_level"],
            content=sign["sign_text"],
            suggested_action=sign["today_advice"],
            estimated_minutes=0,
            can_add_to_task_board=bool(sign.get("action")),
            project_id=project_id if project_id is not None else self.project_id,
        )
        return {**sign, "id": item_id}

    def generate_random_task(self, project_id: Optional[int] = None) -> Dict[str, Any]:
        task = self.motivation_agent.generate_random_task()
        item_id = self.motivation_repository.create_item(
            sign_type="random_task",
            sign_level="",
            content=task["title"],
            suggested_action=task.get("reason", ""),
            estimated_minutes=int(task.get("estimated_minutes") or 0),
            project_id=project_id if project_id is not None else self.project_id,
        )
        return {**task, "id": item_id}

    def generate_soothing_task(
        self,
        user_state: str,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        task = self.motivation_agent.generate_soothing_task(user_state)
        item_id = self.motivation_repository.create_item(
            sign_type="soothing_task",
            sign_level="",
            content=task["title"],
            suggested_action=task.get("reason", ""),
            estimated_minutes=int(task.get("estimated_minutes") or 0),
            project_id=project_id if project_id is not None else self.project_id,
        )
        return {**task, "id": item_id}

