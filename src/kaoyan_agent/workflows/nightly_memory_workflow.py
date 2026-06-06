from datetime import datetime
from typing import Any, Dict, List, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryAgent
from kaoyan_agent.repositories.agent_runs import AgentRunRepository
from kaoyan_agent.repositories.graphs import DailyMemoryGraphRepository
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.nightly_review_repository import NightlyReviewRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository
from kaoyan_agent.schemas.contracts import NightlyWorkflowResult
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput


def today_str() -> str:
    return datetime.now().astimezone().date().isoformat()


class NightlyMemoryWorkflow:
    """夜间记忆更新的业务编排层。

    负责读取当天证据、调用 NightlyMemoryAgent、保存 nightly review，并把
    候选问题、候选记忆和每日记忆图分别落到对应表中。
    """

    workflow_name = "nightly_memory"

    def __init__(
        self,
        settings: Settings | None = None,
        nightly_repository: NightlyReviewRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
        memory_repository: MemoryRepository | None = None,
        problem_repository: ProblemRepository | None = None,
        graph_repository: DailyMemoryGraphRepository | None = None,
        agent_run_repository: AgentRunRepository | None = None,
    ):
        self.settings = settings or get_settings()
        self.nightly_repository = nightly_repository or NightlyReviewRepository()
        self.raw_event_repository = raw_event_repository or RawEventRepository()
        self.memory_repository = memory_repository or MemoryRepository()
        self.problem_repository = problem_repository or ProblemRepository()
        self.graph_repository = graph_repository or DailyMemoryGraphRepository()
        self.agent_run_repository = agent_run_repository or AgentRunRepository()

    def run(
        self,
        review_date: str | None = None,
        project_id: Optional[int] = None,
    ) -> NightlyWorkflowResult:
        """执行一次指定日期的夜间复盘，并返回本次落库摘要。"""
        return self.run_for_project(project_id=project_id, review_date=review_date)

    def run_for_project(
        self,
        project_id: Optional[int],
        review_date: str | None = None,
    ) -> NightlyWorkflowResult:
        """执行一次指定日期的夜间复盘。

        project_id is retained only as a database compatibility filter for
        historical callers. The current UI calls this without a project scope.
        """

        review_date = review_date or today_str()
        # 这四类输入共同构成“今天发生了什么”和“已有长期背景是什么”。
        sessions = self.nightly_repository.list_sessions_by_date(
            review_date,
            project_id=project_id,
        )
        conversations = self.nightly_repository.list_conversations_by_date(
            review_date,
            project_id=project_id,
        )
        raw_events = self.raw_event_repository.list_by_project_and_date(
            project_id=project_id,
            date_str=review_date,
        )
        memories = self.memory_repository.list(project_id=project_id)
        open_problems = self.problem_repository.list_open(project_id=project_id)

        # Agent 只生成结构化判断；是否入库和怎么记录操作由 workflow 控制。
        agent_result = NightlyMemoryAgent(self.settings).run(
            review_date=review_date,
            sessions=sessions,
            conversations=conversations,
            memories=memories,
            open_problems=open_problems,
        )
        output = agent_result.output
        result = output.model_dump()
        # 不论解析是否成功，都保存 raw_response/parse_status，方便页面展示和排错。
        review_id = self.nightly_repository.create(
            review_date=review_date,
            result=result,
            raw_response=agent_result.raw_response,
            parse_status=agent_result.parse_status,
            error_message=agent_result.error_message,
            project_id=project_id,
        )

        inserted_problem_ids = []
        inserted_memory_ids = []
        if agent_result.parse_status == "success":
            inserted_problem_ids = self.save_problems(
                problems=result.get("discovered_problems", []),
                review_id=review_id,
                project_id=project_id,
            )
            inserted_memory_ids = self.save_memories(
                memories=result.get("memory_updates", []),
                review_id=review_id,
                project_id=project_id,
            )
        daily_memory_graph_id = self.save_daily_memory_graph(
            review_date=review_date,
            review_id=review_id,
            output=output,
            raw_events=raw_events,
        )
        self.agent_run_repository.create(
            agent_name="NightlyMemoryAgent",
            workflow_name=self.workflow_name,
            request={
                "review_date": review_date,
                "project_id": project_id,
                "sessions_count": len(sessions),
                "conversations_count": len(conversations),
                "raw_events_count": len(raw_events),
            },
            response=result,
            raw_response=agent_result.raw_response,
            parse_status=agent_result.parse_status,
            error_message=agent_result.error_message,
            project_id=project_id,
        )

        return NightlyWorkflowResult(
            review_id=review_id,
            review_date=review_date,
            parse_status=agent_result.parse_status,
            sessions_count=len(sessions),
            conversations_count=len(conversations),
            raw_events_count=len(raw_events),
            inserted_problem_ids=inserted_problem_ids,
            inserted_memory_ids=inserted_memory_ids,
            daily_memory_graph_id=daily_memory_graph_id,
            error_message=agent_result.error_message,
            result=output,
        )

    def save_problems(
        self,
        problems: List[Any],
        review_id: int,
        project_id: Optional[int] = None,
    ) -> List[int]:
        """保存 LLM 认为值得进入 Problem Board 的候选问题。"""

        inserted_ids = []
        for problem in problems:
            if not isinstance(problem, dict):
                continue
            operation = str(problem.get("operation") or "insert")
            if operation == "skip":
                self.problem_repository.record_operation(
                    operation="skip",
                    candidate=problem,
                    review_id=review_id,
                    reason=str(problem.get("reason") or ""),
                )
                continue
            problem_id = self.problem_repository.create(
                problem,
                review_id=review_id,
                project_id=project_id,
            )
            self.problem_repository.record_operation(
                operation=operation,
                candidate=problem,
                review_id=review_id,
                problem_id=problem_id,
                reason=str(problem.get("reason") or problem.get("root_cause") or ""),
            )
            inserted_ids.append(problem_id)
        return inserted_ids

    def save_memories(
        self,
        memories: List[Any],
        review_id: int,
        project_id: Optional[int] = None,
    ) -> List[int]:
        """保存通过记忆门控的候选长期记忆，并记录候选操作。"""

        inserted_ids = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            operation = str(memory.get("operation") or "insert")
            memory_id = self.memory_repository.create(
                memory,
                review_id=review_id,
                project_id=project_id,
            )
            self.memory_repository.record_operation(
                operation=operation,
                candidate=memory,
                review_id=review_id,
                memory_id=memory_id,
                reason=str(memory.get("reason") or ""),
            )
            if memory_id:
                inserted_ids.append(memory_id)
        return inserted_ids

    def save_daily_memory_graph(
        self,
        review_date: str,
        review_id: int,
        output: NightlyMemoryUpdateOutput,
        raw_events: List[Dict[str, Any]],
    ) -> int:
        """把 raw event、关键事件、问题候选和记忆候选串成当日记忆图。"""

        result = output.model_dump()
        nodes = []
        edges = []
        for event in raw_events:
            nodes.append(
                {
                    "node_id": f"event:{event['id']}",
                    "node_type": "raw_event",
                    "ref_id": event["id"],
                    "content": event.get("content", ""),
                }
            )
        for index, key_event in enumerate(result.get("key_events", []), start=1):
            node_id = f"key_event:{index}"
            nodes.append(
                {
                    "node_id": node_id,
                    "node_type": "key_event",
                    "content": key_event,
                }
            )
            if raw_events:
                edges.append(
                    {
                        "source": f"event:{raw_events[-1]['id']}",
                        "target": node_id,
                        "relation_type": "supports",
                    }
                )
        for index, problem in enumerate(result.get("discovered_problems", []), start=1):
            nodes.append(
                {
                    "node_id": f"problem_candidate:{index}",
                    "node_type": "problem_candidate",
                    "content": problem,
                }
            )
        for index, memory in enumerate(result.get("memory_updates", []), start=1):
            nodes.append(
                {
                    "node_id": f"memory_candidate:{index}",
                    "node_type": "memory_candidate",
                    "content": memory,
                }
            )

        return self.graph_repository.create(
            graph_date=review_date,
            nodes=nodes,
            edges=edges,
            summary=str(result.get("daily_summary") or ""),
            source_event_ids=[int(event["id"]) for event in raw_events],
            review_id=review_id,
        )

