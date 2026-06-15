from typing import Any, Dict, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.agents.motivation import MotivationAgent
from kaoyan_agent.agents.practice_review import PracticeReviewAgent
from kaoyan_agent.repositories.motivation import MotivationRepository
from kaoyan_agent.repositories.practice_review import PracticeReviewRepository
from kaoyan_agent.repositories.score import ScoreRepository
from kaoyan_agent.repositories.study_tasks import StudyTaskRepository
from kaoyan_agent.agents.review_generator import ReviewGeneratorAgent, ReviewHintList

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
        self.review_generator = ReviewGeneratorAgent(self.settings)


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


    def generate_review_hints(
        self,
        question: str = "",
        subject: str = "",
        chapter: str = "",
        user_reason: str = "",
        from_problem_id: int = None,
    ) -> ReviewHintList:
        """生成复刷提示（不生成具体题目）"""
        
        from_problem = None
        if from_problem_id:
            from_problem = self._get_problem(from_problem_id)
        
        return self.review_generator.generate_hints(
            question=question,
            subject=subject,
            chapter=chapter,
            user_reason=user_reason,
            from_problem=from_problem,
        )

    def _get_problem(self, problem_id: int):
        """获取单个问题"""
        from contextlib import closing
        from kaoyan_agent.db.database import get_connection
        
        with closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT id, subject, description, root_cause, suggested_action FROM problem_board WHERE id = ?",
                (problem_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_review_task_from_problem(self, problem_id: int) -> int:
        """根据问题板中的问题生成复习任务"""
        problem = self._get_problem(problem_id)
        if not problem:
            raise ValueError(f"Problem {problem_id} not found")
        
        title = f"复刷：{problem.get('subject', '')} - {problem.get('description', '')[:30]}"
        return self.task_repository.create(
            title=title,
            subject=problem.get("subject", ""),
            estimated_minutes=15,
            source="problem_board",
            related_problem_id=problem_id,
            scheduled_date=self._today_str(),
            project_id=self.project_id,
        )

    def _today_str(self) -> str:
        from datetime import datetime
        return datetime.now().astimezone().date().isoformat()

    def generate_soothing_message(self, user_state: str = "") -> Dict[str, Any]:
        """生成安抚签（只包含安抚语句，不含任务）"""
        from kaoyan_agent.agents.soothing_agent import SoothingAgent
        agent = SoothingAgent(self.settings)
        result = agent.generate(user_state)
        return result.model_dump()

    def analyze_score_trend(self, subject: str) -> Optional[Dict[str, Any]]:
        """分析单科分数趋势并给出建议"""
        from kaoyan_agent.agents.score_analyzer import ScoreAnalyzerAgent
        
        records = self.score_repository.list_records(subject=subject, limit=20)
        if len(records) < 2:
            return None
        
        analyzer = ScoreAnalyzerAgent(self.settings)
        result = analyzer.analyze(subject, records)
        
        if result:
            # 保存分析报告
            report_id = self.score_repository.create_analysis_report(
                subject=subject,
                report_date=self._today_str(),
                latest_score=records[0].get('score'),
                risk_level=result.risk_level,
                ai_suggestion=result.suggestion,
                raw_result=result.model_dump(),
                project_id=self.project_id,
            )
            return {
                "trend": result.trend,
                "suggestion": result.suggestion,
                "risk_level": result.risk_level,
                "focus_points": result.focus_points,
                "report_id": report_id
            }
        return None

    def analyze_score_trend(self, subject: str) -> Optional[Dict[str, Any]]:
        """分析单科分数趋势并给出建议"""
        from kaoyan_agent.agents.score_analyzer import ScoreAnalyzerAgent
        
        # 获取记录并按日期正序排列
        records = self.score_repository.list_records(subject=subject, limit=50)
        if len(records) < 2:
            return None
        
        # 按日期升序（最早的在前）
        records_sorted = sorted(records, key=lambda x: x.get('exam_date', ''))
        
        analyzer = ScoreAnalyzerAgent(self.settings)
        result = analyzer.analyze(subject, records_sorted)
        
        if result:
            # 保存分析报告
            report_id = self.score_repository.create_analysis_report(
                subject=subject,
                report_date=self._today_str(),
                latest_score=records_sorted[-1].get('score'),
                risk_level=result.risk_level,
                ai_suggestion=result.suggestion,
                raw_result=result.model_dump(),
                project_id=self.project_id,
            )
            return {
                "trend": result.trend,
                "suggestion": result.suggestion,
                "risk_level": result.risk_level,
                "focus_points": result.focus_points,
                "report_id": report_id
            }
        return None

    def create_task_with_priority(
        self,
        title: str,
        subject: str = "",
        estimated_minutes: int = 0,
        priority: int = 2,  # 1低 2中 3高
        source: str = "",
        scheduled_date: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> int:
        """创建带优先级的任务"""
        # 如果 study_tasks 表有 priority 字段，可以保存
        # 目前先保存到 review_priority 字段
        return self.task_repository.create(
            title=title,
            subject=subject,
            estimated_minutes=estimated_minutes,
            source=source,
            status="todo",
            scheduled_date=scheduled_date or self._today_str(),
            project_id=project_id if project_id is not None else self.project_id,
        )

    def generate_soothing_message(self, user_state: str = "") -> Dict[str, Any]:
        """生成安抚签（安抚语句 + 可选小任务 + 小游戏入口）"""
        return self.motivation_agent.generate_soothing(user_state)
