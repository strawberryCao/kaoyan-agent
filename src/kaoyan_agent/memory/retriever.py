import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.schemas.contracts import RetrievedItem, RouterDecision


def tokenize(text: str) -> set[str]:
    """轻量分词：英文按词，中文按单字，用于 MVP 阶段的关键词重叠检索。"""

    words = set(re.findall(r"[A-Za-z0-9_]+", text.lower()))
    chinese_chars = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    return words | chinese_chars


def overlap_score(query: str, content: str) -> float:
    """计算查询词在候选内容中的覆盖比例。"""

    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    content_tokens = tokenize(content)
    return len(query_tokens & content_tokens) / max(1, len(query_tokens))


def time_score(updated_at: str) -> float:
    """越近期的 memory/problem 得分越高，用于简单的时间衰减。"""

    if not updated_at:
        return 0.0
    try:
        updated = datetime.fromisoformat(updated_at)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    days = max(0.0, (datetime.now(timezone.utc) - updated).total_seconds() / 86400)
    return 1 / (1 + days)


class MemoryRetriever:
    """从长期记忆和开放问题中取回在线回答可用的上下文。

    当前实现是课程 MVP 的轻量检索：关键词重叠 + 时间 + 有效性 + 问题热度。
    它不是向量数据库，也不负责写入或合并记忆。
    """

    def __init__(
        self,
        memory_repository: MemoryRepository | None = None,
        problem_repository: ProblemRepository | None = None,
    ):
        self.memory_repository = memory_repository or MemoryRepository()
        self.problem_repository = problem_repository or ProblemRepository()

    def retrieve(
        self,
        query: str,
        decision: RouterDecision,
        limit: int = 8,
        project_id: int | None = None,
    ) -> List[RetrievedItem]:
        """根据 RouterDecision 的权重返回得分最高的 memory/problem。"""

        candidates: List[RetrievedItem] = []
        weights = decision.retrieval_weights or {}

        # 长期记忆只取 active/pending_confirm，避免把废弃记忆重新注入回答。
        for memory in self.memory_repository.list(limit=80, project_id=project_id):
            if memory.get("status", "active") not in {"active", "pending_confirm"}:
                continue
            content = str(memory.get("content") or "")
            candidates.append(
                self.score_item(
                    query=query,
                    source_type="memory",
                    source_id=memory.get("id"),
                    content=content,
                    metadata=memory,
                    weights=weights,
                )
            )

        # Problem Board 里的开放问题也可作为上下文，帮助回答延续干预策略。
        for problem in self.problem_repository.list_open(project_id=project_id):
            content = "；".join(
                [
                    str(problem.get("problem_type") or ""),
                    str(problem.get("subject") or ""),
                    str(problem.get("description") or ""),
                    str(problem.get("root_cause") or ""),
                    str(problem.get("suggested_action") or ""),
                ]
            )
            candidates.append(
                self.score_item(
                    query=query,
                    source_type="problem",
                    source_id=problem.get("id"),
                    content=content,
                    metadata=problem,
                    weights=weights,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return [item for item in candidates[:limit] if item.score > 0]

    def score_item(
        self,
        query: str,
        source_type: str,
        source_id: int | None,
        content: str,
        metadata: Dict[str, Any],
        weights: Dict[str, float],
    ) -> RetrievedItem:
        """把一个候选 memory/problem 转成带解释性分数的 RetrievedItem。"""

        matching = overlap_score(query, content)
        recency = time_score(str(metadata.get("updated_at") or metadata.get("created_at") or ""))
        effectiveness = float(metadata.get("effectiveness_score") or 0.0)
        heat = 0.1 if source_type == "problem" else 0.05
        score = (
            weights.get("matching_score", 0.55) * matching
            + weights.get("time_score", 0.2) * recency
            + weights.get("effectiveness_score", 0.2) * effectiveness
            + weights.get("heat_score", 0.05) * heat
        )
        score_metadata = {
            **metadata,
            "matching_score": matching,
            "time_score": recency,
            "effectiveness_score": effectiveness,
            "heat_score": heat,
        }
        return RetrievedItem(
            source_type=source_type,
            source_id=source_id,
            content=content,
            score=round(score, 4),
            metadata=score_metadata,
        )

