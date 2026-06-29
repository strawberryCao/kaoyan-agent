import json
from datetime import datetime
from typing import Any, Callable, List, Optional

from kaoyan_agent.memory.retriever import MemoryRetriever
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.study_tasks import StudyTaskRepository
from kaoyan_agent.schemas.contracts import RouterDecision

try:
    from langchain_core.tools import tool
except ModuleNotFoundError:
    def tool(func: Callable[..., str]) -> Callable[..., str]:
        return func


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _clamp_limit(limit: int, default: int, maximum: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(maximum, value))


def build_readonly_chat_tools(project_id: Optional[int] = None) -> List[Any]:
    """Build LangChain-compatible read-only tools for ChatAgent."""

    problem_repository = ProblemRepository()
    task_repository = StudyTaskRepository()
    memory_retriever = MemoryRetriever()

    @tool
    def list_open_problems_tool(limit: int = 5) -> str:
        """List open Problem Board items for context; this tool never writes data."""

        max_items = _clamp_limit(limit, default=5, maximum=20)
        problems = problem_repository.list_open(project_id=project_id)[:max_items]
        compact = [
            {
                "id": problem.get("id"),
                "problem_type": problem.get("problem_type"),
                "subject": problem.get("subject"),
                "description": problem.get("description"),
                "severity": problem.get("severity"),
                "value_score": problem.get("value_score"),
                "suggested_action": problem.get("suggested_action"),
                "status": problem.get("status"),
            }
            for problem in problems
        ]
        return _json_text(compact)

    @tool
    def list_today_tasks_tool(limit: int = 10) -> str:
        """List today's study tasks for context; this tool never writes data."""

        max_items = _clamp_limit(limit, default=10, maximum=30)
        today = datetime.now().astimezone().date().isoformat()
        tasks = task_repository.list(
            date_str=today,
            limit=max_items,
            project_id=project_id,
        )
        compact = [
            {
                "id": task.get("id"),
                "title": task.get("title"),
                "subject": task.get("subject"),
                "status": task.get("status"),
                "estimated_minutes": task.get("estimated_minutes"),
                "source": task.get("source"),
                "related_problem_id": task.get("related_problem_id"),
            }
            for task in tasks
        ]
        return _json_text(compact)

    @tool
    def search_memory_tool(query: str, limit: int = 5) -> str:
        """Search long-term memory and open problems for context; this tool is read-only."""

        query_text = str(query or "").strip()
        if not query_text:
            return _json_text([])
        max_items = _clamp_limit(limit, default=5, maximum=20)
        decision = RouterDecision(
            route="chat",
            need_memory=True,
            retrieval_weights={
                "matching_score": 0.55,
                "time_score": 0.2,
                "effectiveness_score": 0.2,
                "heat_score": 0.05,
            },
            reason="ChatAgent read-only memory search tool",
        )
        items = memory_retriever.retrieve(
            query=query_text,
            decision=decision,
            limit=max_items,
            project_id=project_id,
        )
        return _json_text([item.to_dict() for item in items])

    return [
        list_open_problems_tool,
        list_today_tasks_tool,
        search_memory_tool,
    ]
