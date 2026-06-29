import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from kaoyan_agent.repositories.graphs import GlobalMemoryGraphRepository
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.skill_memory_repository import SkillMemoryRepository
from kaoyan_agent.schemas.contracts import RetrievedItem, RouterDecision
from kaoyan_agent.services.embedding_client import EmbeddingClient, cosine_similarity
from kaoyan_agent.services.graph_store import GraphStore
from kaoyan_agent.services.vector_store import VectorStore


def tokenize(text: str) -> set[str]:
    """Lightweight tokenizer for keyword-overlap fallback retrieval."""

    words = set(re.findall(r"[A-Za-z0-9_]+", text.lower()))
    chinese_chars = {char for char in text if "\u4e00" <= char <= "\u9fff"}
    return words | chinese_chars


def overlap_score(query: str, content: str) -> float:
    """Calculate how much of the query appears in a candidate document."""

    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    content_tokens = tokenize(content)
    return len(query_tokens & content_tokens) / max(1, len(query_tokens))


def time_score(updated_at: str) -> float:
    """Prefer recently updated memories/problems."""

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
    """Retrieve online context from Chroma/Neo4j with lexical fallback.

    Chroma available: embedding -> Chroma top_k -> score fusion.
    Chroma unavailable: temporary fallback to lightweight explainable retrieval:
    keyword overlap + time + effectiveness + heat.
    """

    def __init__(
        self,
        memory_repository: MemoryRepository | None = None,
        problem_repository: ProblemRepository | None = None,
        skill_repository: SkillMemoryRepository | None = None,
        graph_repository: GlobalMemoryGraphRepository | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
    ):
        self.memory_repository = memory_repository or MemoryRepository()
        self.problem_repository = problem_repository or ProblemRepository()
        self.skill_repository = skill_repository or SkillMemoryRepository()
        self.graph_repository = graph_repository or GlobalMemoryGraphRepository()
        self.embedding_client = embedding_client or EmbeddingClient()
        self.vector_store = vector_store or VectorStore(embedding_client=self.embedding_client)
        self.graph_store = graph_store or GraphStore()

    def retrieve(
        self,
        query: str,
        decision: RouterDecision,
        limit: int = 8,
        project_id: int | None = None,
    ) -> List[RetrievedItem]:
        """Return the highest scoring memory/problem context for a query."""

        vector_status = self.vector_store.get_status()
        if vector_status.get("available"):
            vector_items = self.retrieve_hybrid(query, decision, limit, project_id)
            if vector_items:
                return vector_items[:limit]
            refreshed_status = self.vector_store.get_status()
            fallback_reason = str(
                getattr(self.vector_store, "_last_error", "")
                or refreshed_status.get("embedding_error")
                or refreshed_status.get("error")
                or "Chroma returned no results"
            )
        else:
            fallback_reason = str(
                vector_status.get("error")
                or vector_status.get("embedding_error")
                or "Chroma unavailable"
            )
        return self.retrieve_keyword(
            query,
            decision,
            limit=limit,
            project_id=project_id,
            fallback_reason=fallback_reason,
        )

    def retrieve_hybrid(
        self,
        query: str,
        decision: RouterDecision,
        limit: int,
        project_id: int | None,
    ) -> List[RetrievedItem]:
        weights = decision.retrieval_weights or {}
        vector_results = self.vector_store.query(query, limit=max(limit * 2, 8), project_id=project_id)
        memories_by_id = {
            int(memory["id"]): memory
            for memory in self.memory_repository.list(limit=120, project_id=project_id)
            if memory.get("status", "active") in {"active", "pending_confirm"}
        }
        problems_by_id = {
            int(problem["id"]): problem
            for problem in self.problem_repository.list_open(project_id=project_id)
        }

        candidates: List[RetrievedItem] = []
        for result in vector_results:
            source_type = str(result.get("source_type") or "")
            source_id = int(result.get("source_id") or 0)
            if source_type == "memory":
                row = memories_by_id.get(source_id)
                if not row:
                    continue
                content = str(row.get("content") or result.get("content") or "")
            elif source_type == "problem":
                row = problems_by_id.get(source_id)
                if not row:
                    continue
                content = self.problem_content(row)
            else:
                continue
            candidates.append(
                self.score_hybrid_item(
                    source_type=source_type,
                    source_id=source_id,
                    content=content,
                    metadata={**row, **dict(result.get("metadata") or {})},
                    weights=weights,
                    vector_similarity=float(result.get("vector_similarity") or 0.0),
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return [item for item in candidates if item.score > 0]

    def retrieve_keyword(
        self,
        query: str,
        decision: RouterDecision,
        limit: int = 8,
        project_id: int | None = None,
        fallback_reason: str = "",
    ) -> List[RetrievedItem]:
        candidates: List[RetrievedItem] = []
        weights = decision.retrieval_weights or {}
        query_embedding = self.embedding_client.encode(query)

        for memory in self.memory_repository.list(limit=80, project_id=project_id):
            if memory.get("status", "active") not in {"active", "pending_confirm"}:
                continue
            content = str(memory.get("content") or "")
            candidates.append(
                self.score_keyword_item(
                    query=query,
                    source_type="memory",
                    source_id=memory.get("id"),
                    content=content,
                    metadata=memory,
                    weights=weights,
                    query_embedding=query_embedding,
                    fallback_reason=fallback_reason,
                )
            )

        for problem in self.problem_repository.list_open(project_id=project_id):
            content = self.problem_content(problem)
            candidates.append(
                self.score_keyword_item(
                    query=query,
                    source_type="problem",
                    source_id=problem.get("id"),
                    content=content,
                    metadata=problem,
                    weights=weights,
                    query_embedding=query_embedding,
                    fallback_reason=fallback_reason,
                )
            )

        for skill in self.skill_repository.list(limit=40):
            content = " | ".join(
                [
                    str(skill.get("skill_name") or ""),
                    str(skill.get("description") or ""),
                    str(skill.get("trigger") or ""),
                    str(skill.get("procedure") or ""),
                ]
            )
            candidates.append(
                self.score_keyword_item(
                    query=query,
                    source_type="skill",
                    source_id=skill.get("id"),
                    content=content,
                    metadata=skill,
                    weights=weights,
                    query_embedding=query_embedding,
                    fallback_reason=fallback_reason,
                )
            )

        for node in self.graph_repository.list_nodes(limit=80):
            content = " | ".join(
                [
                    str(node.get("node_type") or ""),
                    str(node.get("title") or ""),
                    str(node.get("content") or ""),
                ]
            )
            candidates.append(
                self.score_keyword_item(
                    query=query,
                    source_type="global_graph",
                    source_id=node.get("id"),
                    content=content,
                    metadata=node,
                    weights=weights,
                    query_embedding=query_embedding,
                    fallback_reason=fallback_reason,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return [item for item in candidates[:limit] if item.score > 0]

    def score_hybrid_item(
        self,
        source_type: str,
        source_id: int,
        content: str,
        metadata: Dict[str, Any],
        weights: Dict[str, float],
        vector_similarity: float,
    ) -> RetrievedItem:
        recency = time_score(str(metadata.get("updated_at") or metadata.get("created_at") or ""))
        effectiveness = float(metadata.get("effectiveness_score") or 0.0)
        heat = self.heat_score(source_type)
        graph_neighbors = self.graph_neighbors(source_type, source_id)
        graph_boost = 0.05 if graph_neighbors.get("edges") else 0.0
        score = (
            weights.get("matching_score", 0.55) * vector_similarity
            + weights.get("time_score", 0.2) * recency
            + weights.get("effectiveness_score", 0.2) * effectiveness
            + weights.get("heat_score", 0.05) * heat
            + graph_boost
        )
        score_metadata = {
            **metadata,
            "retrieval_backend": "chroma_hybrid",
            "vector_used": True,
            "graph_used": bool(graph_neighbors.get("edges")),
            "vector_similarity": vector_similarity,
            "matching_score": vector_similarity,
            "time_score": recency,
            "effectiveness_score": effectiveness,
            "heat_score": heat,
            "graph_boost": graph_boost,
            "graph_neighbors": graph_neighbors,
        }
        return RetrievedItem(
            source_type=source_type,
            source_id=source_id,
            content=content,
            score=round(score, 4),
            metadata=score_metadata,
        )

    def score_keyword_item(
        self,
        query: str,
        source_type: str,
        source_id: int | None,
        content: str,
        metadata: Dict[str, Any],
        weights: Dict[str, float],
        query_embedding: List[float] | None = None,
        fallback_reason: str = "",
    ) -> RetrievedItem:
        candidate_embedding = metadata.get("embedding") or []
        if query_embedding and candidate_embedding:
            matching = cosine_similarity(query_embedding, candidate_embedding)
        else:
            matching = overlap_score(query, content)
        recency = time_score(str(metadata.get("updated_at") or metadata.get("created_at") or ""))
        effectiveness = float(metadata.get("effectiveness_score") or 0.0)
        heat = self.heat_score(source_type)
        score = (
            weights.get("matching_score", 0.55) * matching
            + weights.get("time_score", 0.2) * recency
            + weights.get("effectiveness_score", 0.2) * effectiveness
            + weights.get("heat_score", 0.05) * heat
        )
        score_metadata = {
            **metadata,
            "retrieval_backend": "keyword_overlap",
            "vector_used": False,
            "graph_used": False,
            "fallback_reason": fallback_reason,
            "vector_similarity": 0.0,
            "matching_score": matching,
            "time_score": recency,
            "effectiveness_score": effectiveness,
            "heat_score": heat,
            "graph_boost": 0.0,
        }
        return RetrievedItem(
            source_type=source_type,
            source_id=source_id,
            content=content,
            score=round(score, 4),
            metadata=score_metadata,
        )

    def graph_neighbors(self, source_type: str, source_id: int) -> Dict[str, Any]:
        if source_type not in {"memory", "problem"}:
            return {"nodes": [], "edges": []}
        status = self.graph_store.get_status()
        if not (status.get("connected") or status.get("available")):
            return {"nodes": [], "edges": [], "status": status}
        return self.graph_store.get_neighbors(self.graph_store.node_key(source_type, source_id), depth=1)

    @staticmethod
    def heat_score(source_type: str) -> float:
        return {
            "problem": 0.1,
            "skill": 0.08,
            "global_graph": 0.07,
        }.get(source_type, 0.05)

    @staticmethod
    def problem_content(problem: Dict[str, Any]) -> str:
        return " | ".join(
            [
                str(problem.get("problem_type") or ""),
                str(problem.get("subject") or ""),
                str(problem.get("description") or ""),
                str(problem.get("root_cause") or ""),
                str(problem.get("suggested_action") or ""),
            ]
        )

