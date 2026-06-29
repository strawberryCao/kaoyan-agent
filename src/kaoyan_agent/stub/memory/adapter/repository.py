from typing import Any, List, Tuple, Dict, Optional
from uuid import uuid4

from ..type import (
    Memory,
    Problem,
    Diary,
    Summary,
)

from ..store import (
    AbstractMemoryStore,
    AbstractProblemStore,
    AbstractDiaryStore,
)

from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.nightly_review_repository import NightlyReviewRepository


class MemoryStoreAdapter(AbstractMemoryStore):
    """基于 MemoryRepository 的 Memory 存储适配器（不支持删除）"""

    def __init__(self, project_id: Optional[int] = None):
        self.repo = MemoryRepository()
        self.project_id = project_id

    def _to_memory(self, row: Dict[str, Any]) -> Memory:
        return Memory(
            uuid=str(row["id"]),
            type=row.get("memory_type", "strategy"),
            content=row.get("content", ""),
            confidence_score=int(row.get("confidence", 0.0) * 100),
            effectiveness_score=row.get("effectiveness_score", 0),
            add_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
            last_used_at=row.get("last_used_at", ""),
            status=row.get("status", "active"),
        )

    def _from_memory(self, memory: Memory) -> Dict[str, Any]:
        return {
            "operation": "insert",
            "memory_type": memory["type"],
            "content": memory["content"],
            "importance": max(1, min(5, memory["confidence_score"] // 20)),
            "confidence": memory["confidence_score"] / 100.0,
            "merge_key": "",
            "reason": "",
            "status": memory["status"],
            "evidence_refs": [],
            "subject": "",
        }

    def add(self, items: List[Memory]) -> None:
        for mem in items:
            self.repo.create(
                memory=self._from_memory(mem),
                project_id=self.project_id,
            )

    def delete(self, ids: List[str]) -> None:
        # MemoryRepository 没有提供 delete 方法，直接报错
        raise NotImplementedError("MemoryRepository does not support delete operation")

    def get_all(self) -> List[Memory]:
        rows = self.repo.list(limit=None, project_id=self.project_id)
        return [self._to_memory(row) for row in rows]

    def similarity_search(
        self, query: str, top_k: int, filter: Dict[str, Any]
    ) -> Tuple[List[Memory], float]:
        all_memories = self.get_all()
        filtered = []
        for mem in all_memories:
            if filter.get("type") and mem["type"] != filter["type"]:
                continue
            if filter.get("status") and mem["status"] != filter["status"]:
                continue
            if query.lower() in mem["content"].lower():
                filtered.append(mem)
        filtered.sort(key=lambda x: x["confidence_score"], reverse=True)
        result = filtered[:top_k]
        score = len(result) / top_k if top_k > 0 else 0.0
        return result, score


class ProblemStoreAdapter(AbstractProblemStore):
    """基于 ProblemRepository 的 Problem 存储适配器（不支持删除）"""

    def __init__(self, project_id: Optional[int] = None):
        self.repo = ProblemRepository()
        self.project_id = project_id

    def _to_problem(self, row: Dict[str, Any]) -> Problem:
        return Problem(
            uuid=str(row["id"]),
            title=row.get("subject", ""),
            description=row.get("description", ""),
            impact_score=row.get("value_score", 0),
            add_at=row.get("created_at", ""),
            status=row.get("status", "open"),
        )

    def _from_problem(self, problem: Problem) -> Dict[str, Any]:
        return {
            "problem_type": "other",
            "subject": problem["title"],
            "description": problem["description"],
            "evidence": [],
            "root_cause": "",
            "severity": max(1, min(5, problem["impact_score"] // 20)),
            "confidence": 0.8,
            "value_score": problem["impact_score"],
            "suggested_action": "",
            "status": problem["status"],
            "evidence_refs": [],
            "merge_key": "",
        }

    def add(self, items: List[Problem]) -> None:
        for prob in items:
            self.repo.create(
                problem=self._from_problem(prob),
                project_id=self.project_id,
            )

    def delete(self, ids: List[str]) -> None:
        # ProblemRepository 没有提供 delete 方法，直接报错
        raise NotImplementedError("ProblemRepository does not support delete operation")

    def get_all(self) -> List[Problem]:
        # ProblemRepository 原生只提供 list_open，这里需要获取所有状态的问题
        # 直接使用项目中的数据库连接查询所有，但不执行删除
        from contextlib import closing
        from kaoyan_agent.db.database import get_connection, rows_to_dicts

        with closing(get_connection()) as conn:
            rows = conn.execute(
                "SELECT id, subject, description, value_score, status, created_at FROM problem_board"
                + (" WHERE project_id = ?" if self.project_id else ""),
                (self.project_id,) if self.project_id else (),
            ).fetchall()
        dicts = rows_to_dicts(rows)
        return [self._to_problem(d) for d in dicts]

    def similarity_search(
        self, query: str, top_k: int, filter: Dict[str, Any]
    ) -> Tuple[List[Problem], float]:
        all_problems = self.get_all()
        filtered = []
        for prob in all_problems:
            if filter.get("status") and prob["status"] != filter["status"]:
                continue
            if (
                query.lower() in prob["title"].lower()
                or query.lower() in prob["description"].lower()
            ):
                filtered.append(prob)
        filtered.sort(key=lambda x: x["impact_score"], reverse=True)
        result = filtered[:top_k]
        score = len(result) / top_k if top_k > 0 else 0.0
        return result, score


class DiaryStoreAdapter(AbstractDiaryStore):
    """基于 NightlyReviewRepository 的 Diary 存储适配器（只读，不支持增删）"""

    def __init__(self, project_id: Optional[int] = None):
        self.repo = NightlyReviewRepository()
        self.project_id = project_id

    def _review_to_diary(self, review: Dict[str, Any]) -> Diary:
        next_actions = review.get("next_actions", [])
        first_action = next_actions[0] if next_actions else {}
        summary: Summary = {
            "summary": review.get("daily_summary", ""),
            "next_action": first_action.get("action", "follow_up"),
            "emotion": "neutral",
            "stress_level": 5,
        }
        new_memories: List[Memory] = []
        updated_memories: List[Memory] = []
        for mem_update in review.get("memory_updates", []):
            mem = Memory(
                uuid=str(uuid4()),
                type=mem_update.get("memory_type", "strategy"),
                content=mem_update.get("content", ""),
                confidence_score=int(mem_update.get("confidence", 0.5) * 100),
                effectiveness_score=0,
                add_at=review["review_date"],
                updated_at=review["review_date"],
                last_used_at=review["review_date"],
                status="active",
            )
            if mem_update.get("operation") == "new":
                new_memories.append(mem)
            else:
                updated_memories.append(mem)
        new_problems: List[Problem] = []
        updated_problems: List[Problem] = []
        for prob_data in review.get("discovered_problems", []):
            prob = Problem(
                uuid=str(uuid4()),
                title=prob_data.get("subject", ""),
                description=prob_data.get("description", ""),
                impact_score=prob_data.get("value_score", 0),
                add_at=review["review_date"],
                status="open",
            )
            new_problems.append(prob)
        return Diary(
            add_at=review["review_date"],
            summary=summary,
            new_memories=new_memories,
            updated_memories=updated_memories,
            new_problems=new_problems,
            updated_problems=updated_problems,
        )

    def add(self, items: List[Diary]) -> None:
        raise NotImplementedError("DiaryStoreAdapter is read-only, add not supported")

    def delete(self, ids: List[str]) -> None:
        raise NotImplementedError(
            "DiaryStoreAdapter is read-only, delete not supported"
        )

    def get_all(self) -> List[Diary]:
        reviews = self.repo.list_latest(limit=1000, project_id=self.project_id)
        return [self._review_to_diary(review) for review in reviews]

    def similarity_search(
        self, query: str, top_k: int, filter: Dict[str, Any]
    ) -> Tuple[List[Diary], float]:
        all_diaries = self.get_all()
        filtered = []
        for diary in all_diaries:
            if query.lower() in diary["summary"]["summary"].lower():
                filtered.append(diary)
        result = filtered[:top_k]
        score = len(result) / top_k if top_k > 0 else 0.0
        return result, score
