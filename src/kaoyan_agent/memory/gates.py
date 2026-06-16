from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional

from kaoyan_agent.memory.embeddings import EmbeddingClient, cosine_similarity
from kaoyan_agent.memory.retriever import overlap_score


@dataclass
class GateDecision:
    operation: str
    candidate: Dict[str, Any]
    target_id: Optional[int] = None
    reason: str = ""
    similarity: float = 0.0
    lexical_score: float = 0.0
    embedding_status: str = "not_called"
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_error: str = ""

    def to_record(self, target_type: str) -> dict[str, Any]:
        return {
            "target_type": target_type,
            "operation": self.operation,
            "target_id": self.target_id,
            "reason": self.reason,
            "similarity": round(self.similarity, 4),
            "lexical_score": round(self.lexical_score, 4),
            "embedding_status": self.embedding_status,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_error": self.embedding_error,
            "error": self.embedding_error,
            "merge_key": str(self.candidate.get("merge_key") or ""),
            "validation_status": "valid",
            "skip_reason": self.reason if self.operation == "skip" else "",
            "evidence_refs": self.candidate.get("evidence_refs") or [],
            "candidate": self.candidate,
        }


class MemoryGateEngine:
    def __init__(self, embedding_client: EmbeddingClient | None = None):
        self.embedding_client = embedding_client or EmbeddingClient()

    def decide_memory(
        self,
        candidate: Dict[str, Any],
        existing: Iterable[Dict[str, Any]],
        exact_match: Optional[Dict[str, Any]] = None,
    ) -> GateDecision:
        candidate = dict(candidate)
        operation = str(candidate.get("operation") or "insert")
        content = str(candidate.get("content") or "").strip()
        if operation == "skip" or not content:
            return self._decision("skip", candidate, reason="empty or skipped memory candidate")
        if not candidate.get("evidence_refs"):
            return self._decision("skip", candidate, reason="memory candidate lacks evidence_refs")
        if float(candidate.get("confidence") or 0.0) < 0.35:
            return self._decision("skip", candidate, reason="memory confidence below gate threshold")

        candidate["embedding"] = candidate.get("embedding") or self.embedding_client.encode(content)
        target_id = candidate.get("target_memory_id")
        if target_id:
            next_operation = operation if operation != "insert" else "update"
            return self._decision(next_operation, candidate, int(target_id), "target_memory_id provided")
        if exact_match:
            return self._decision(
                "merge",
                candidate,
                int(exact_match["id"]),
                "merge_key matched existing memory",
                1.0,
                1.0,
            )

        best, similarity, lexical_score = self._best_match(candidate, existing, self._memory_text)
        if best and similarity >= 0.82:
            return self._decision(
                "merge",
                candidate,
                int(best["id"]),
                "memory similarity above merge threshold",
                similarity,
                lexical_score,
            )
        return self._decision(
            "insert",
            candidate,
            reason="new long-term memory candidate",
            similarity=similarity,
            lexical_score=lexical_score,
        )

    def decide_problem(
        self,
        candidate: Dict[str, Any],
        existing: Iterable[Dict[str, Any]],
        exact_match: Optional[Dict[str, Any]] = None,
    ) -> GateDecision:
        candidate = dict(candidate)
        operation = str(candidate.get("operation") or "insert")
        description = str(candidate.get("description") or "").strip()
        evidence = candidate.get("evidence") or candidate.get("evidence_refs") or []
        if operation == "skip" or not description or not evidence:
            return self._decision("skip", candidate, reason="problem candidate lacks description or evidence")
        if float(candidate.get("confidence") or 0.0) < 0.35:
            return self._decision("skip", candidate, reason="problem confidence below gate threshold")

        candidate["embedding"] = candidate.get("embedding") or self.embedding_client.encode(self._problem_text(candidate))
        target_id = candidate.get("target_problem_id")
        if target_id:
            next_operation = operation if operation != "insert" else "update"
            return self._decision(next_operation, candidate, int(target_id), "target_problem_id provided")
        if exact_match:
            return self._decision(
                "merge",
                candidate,
                int(exact_match["id"]),
                "merge_key matched existing problem",
                1.0,
                1.0,
            )

        best, similarity, lexical_score = self._best_match(candidate, existing, self._problem_text)
        if best and similarity >= 0.80:
            return self._decision(
                "merge",
                candidate,
                int(best["id"]),
                "problem similarity above merge threshold",
                similarity,
                lexical_score,
            )
        return self._decision(
            "insert",
            candidate,
            reason="new problem candidate",
            similarity=similarity,
            lexical_score=lexical_score,
        )

    def decide_skill(
        self,
        candidate: Dict[str, Any],
        existing: Iterable[Dict[str, Any]],
        exact_match: Optional[Dict[str, Any]] = None,
    ) -> GateDecision:
        candidate = dict(candidate)
        operation = str(candidate.get("operation") or "insert")
        skill_name = str(candidate.get("skill_name") or "").strip()
        has_procedure = bool(candidate.get("procedure"))
        if operation == "skip" or not skill_name or not has_procedure:
            return self._decision("skip", candidate, reason="skill candidate lacks name or procedure")
        if not (candidate.get("evidence") or candidate.get("evidence_refs")):
            return self._decision("skip", candidate, reason="skill candidate lacks evidence")
        if float(candidate.get("confidence") or 0.0) < 0.45:
            return self._decision("skip", candidate, reason="skill confidence below gate threshold")

        candidate["merge_key"] = str(candidate.get("merge_key") or skill_name)
        candidate["embedding"] = candidate.get("embedding") or self.embedding_client.encode(self._skill_text(candidate))
        target_id = candidate.get("target_skill_id")
        if target_id:
            next_operation = operation if operation != "insert" else "update"
            return self._decision(next_operation, candidate, int(target_id), "target_skill_id provided")
        if exact_match:
            return self._decision(
                "merge",
                candidate,
                int(exact_match["id"]),
                "merge_key or skill_name matched existing skill",
                1.0,
                1.0,
            )

        best, similarity, lexical_score = self._best_match(candidate, existing, self._skill_text)
        if best and similarity >= 0.84:
            return self._decision(
                "merge",
                candidate,
                int(best["id"]),
                "skill similarity above merge threshold",
                similarity,
                lexical_score,
            )
        return self._decision(
            "insert",
            candidate,
            reason="new reusable skill memory",
            similarity=similarity,
            lexical_score=lexical_score,
        )

    def _decision(
        self,
        operation: str,
        candidate: Dict[str, Any],
        target_id: Optional[int] = None,
        reason: str = "",
        similarity: float = 0.0,
        lexical_score: float = 0.0,
    ) -> GateDecision:
        embedding_metadata = self.embedding_client.status_metadata()
        return GateDecision(
            operation=operation,
            candidate=candidate,
            target_id=target_id,
            reason=reason,
            similarity=similarity,
            lexical_score=lexical_score,
            embedding_status=str(embedding_metadata.get("embedding_status") or "not_called"),
            embedding_provider=str(embedding_metadata.get("embedding_provider") or ""),
            embedding_model=str(embedding_metadata.get("embedding_model") or ""),
            embedding_error=str(embedding_metadata.get("embedding_error") or ""),
        )

    def _best_match(
        self,
        candidate: Dict[str, Any],
        existing: Iterable[Dict[str, Any]],
        text_builder: Callable[[Dict[str, Any]], str],
    ) -> tuple[Optional[Dict[str, Any]], float, float]:
        candidate_text = text_builder(candidate)
        candidate_embedding = candidate.get("embedding") or []
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        best_lexical_score = 0.0
        for item in existing:
            item_text = text_builder(item)
            item_embedding = item.get("embedding") or []
            lexical_score = overlap_score(candidate_text, item_text)
            if candidate_embedding and item_embedding:
                score = cosine_similarity(candidate_embedding, item_embedding)
            else:
                score = lexical_score
            if score > best_score:
                best = item
                best_score = score
                best_lexical_score = lexical_score
        return best, best_score, best_lexical_score

    @staticmethod
    def _memory_text(item: Dict[str, Any]) -> str:
        return " | ".join(
            [
                str(item.get("memory_type") or ""),
                str(item.get("subject") or ""),
                str(item.get("content") or ""),
                str(item.get("reason") or ""),
            ]
        )

    @staticmethod
    def _problem_text(item: Dict[str, Any]) -> str:
        evidence = item.get("evidence") or []
        return " | ".join(
            [
                str(item.get("problem_type") or ""),
                str(item.get("subject") or ""),
                str(item.get("description") or ""),
                str(item.get("root_cause") or ""),
                str(item.get("suggested_action") or ""),
                " | ".join(str(value) for value in evidence),
            ]
        )

    @staticmethod
    def _skill_text(item: Dict[str, Any]) -> str:
        return " | ".join(
            [
                str(item.get("skill_name") or ""),
                str(item.get("description") or ""),
                str(item.get("trigger") or item.get("trigger_json") or ""),
                str(item.get("procedure") or item.get("procedure_json") or ""),
            ]
        )
