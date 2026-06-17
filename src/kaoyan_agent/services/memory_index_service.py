from __future__ import annotations

from typing import Any, Dict, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.services.graph_store import GraphStore
from kaoyan_agent.services.vector_store import VectorStore


class MemoryIndexService:
    """Synchronize SQLite memory/problem rows to optional index backends."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        vector_store: Optional[VectorStore] = None,
        graph_store: Optional[GraphStore] = None,
    ):
        self.settings = settings or get_settings()
        self.vector_store = vector_store or VectorStore(self.settings)
        self.graph_store = graph_store or GraphStore(self.settings)

    def sync_memory(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        if not memory.get("id"):
            return {"status": "skipped", "reason": "missing memory id"}
        vector = self.vector_store.upsert_memory(memory)
        node_key = self.graph_store.node_key("memory", int(memory["id"]))
        graph_node = self.graph_store.upsert_node(
            node_key=node_key,
            node_type="memory",
            ref_type="memory",
            ref_id=int(memory["id"]),
            title=str(memory.get("memory_type") or f"Memory {memory['id']}"),
            content=str(memory.get("content") or ""),
            metadata={
                "project_id": memory.get("project_id"),
                "review_id": memory.get("review_id"),
                "merge_key": memory.get("merge_key") or "",
                "status": memory.get("status") or "active",
            },
            embedding=memory.get("embedding") or memory.get("embedding_json") or [],
            status=str(memory.get("status") or "active"),
        )
        graph_edges = self.sync_evidence_edges(
            target_node_key=node_key,
            target_type="memory",
            evidence_refs=memory.get("evidence_refs") or [],
        )
        return {"vector": vector, "graph_node": graph_node, "graph_edges": graph_edges}

    def sync_nightly_memories_to_chroma(
        self,
        memories: list[Dict[str, Any]],
        *,
        review_id: int,
        review_date: str,
    ) -> Dict[str, Any]:
        """Upsert nightly-created episodic/semantic memories into Chroma.

        SQLite is the source of truth; failures here are captured and returned
        for nightly_reviews.index_sync_status_json instead of being raised.
        """

        results: list[Dict[str, Any]] = []
        errors: list[Dict[str, Any]] = []
        upserted = 0
        skipped = 0
        for memory in memories:
            if not memory.get("id"):
                skipped += 1
                results.append({"status": "skipped", "reason": "missing memory id"})
                continue
            metadata = {
                "memory_type": memory.get("memory_type") or "",
                "date": review_date,
                "source": "nightly_review",
                "review_id": review_id,
                **dict(memory.get("metadata") or {}),
            }
            try:
                result = self.vector_store.upsert_memory(memory, metadata=metadata)
            except Exception as exc:  # defensive boundary around optional index backend
                result = {"status": "failed", "error": str(exc)}
            results.append(result)
            status = str(result.get("status") or "")
            if status == "success":
                upserted += 1
            elif status == "skipped":
                skipped += 1
            else:
                errors.append(
                    {
                        "memory_id": memory.get("id"),
                        "status": status,
                        "error": result.get("error") or result.get("reason") or "",
                    }
                )
        return self._batch_status(
            backend="chroma",
            attempted=len(memories),
            upserted=upserted,
            skipped=skipped,
            results=results,
            errors=errors,
        )

    def sync_problem(self, problem: Dict[str, Any]) -> Dict[str, Any]:
        if not problem.get("id"):
            return {"status": "skipped", "reason": "missing problem id"}
        vector = self.vector_store.upsert_problem(problem)
        node_key = self.graph_store.node_key("problem", int(problem["id"]))
        content = " | ".join(
            [
                str(problem.get("problem_type") or ""),
                str(problem.get("subject") or ""),
                str(problem.get("description") or ""),
                str(problem.get("root_cause") or ""),
                str(problem.get("suggested_action") or ""),
            ]
        )
        graph_node = self.graph_store.upsert_node(
            node_key=node_key,
            node_type="problem",
            ref_type="problem",
            ref_id=int(problem["id"]),
            title=str(problem.get("description") or f"Problem {problem['id']}"),
            content=content,
            metadata={
                "project_id": problem.get("project_id"),
                "review_id": problem.get("review_id"),
                "merge_key": problem.get("merge_key") or "",
                "status": problem.get("status") or "open",
            },
            embedding=problem.get("embedding") or problem.get("embedding_json") or [],
            status=str(problem.get("status") or "open"),
        )
        graph_edges = self.sync_evidence_edges(
            target_node_key=node_key,
            target_type="problem",
            evidence_refs=problem.get("evidence_refs") or [],
        )
        return {"vector": vector, "graph_node": graph_node, "graph_edges": graph_edges}

    def sync_daily_graph_to_neo4j(
        self,
        *,
        daily_graph: Dict[str, Any],
        raw_events: list[Dict[str, Any]],
        memories: list[Dict[str, Any]],
        problems: list[Dict[str, Any]],
        review_id: int,
        review_date: str,
    ) -> Dict[str, Any]:
        """Sync the formal daily graph and persisted targets to GraphStore."""

        results: list[Dict[str, Any]] = []
        errors: list[Dict[str, Any]] = []
        node_count = 0
        edge_count = 0
        graph_id = daily_graph.get("id")
        daily_key = f"daily_memory_graph:{graph_id or review_id}"

        def record(result: Dict[str, Any], item_key: str) -> None:
            nonlocal node_count, edge_count
            results.append(result)
            status = str(result.get("status") or "")
            if status != "success":
                errors.append(
                    {
                        "item_key": item_key,
                        "status": status,
                        "error": result.get("error") or result.get("reason") or "",
                    }
                )

        def upsert_node(**kwargs: Any) -> str:
            nonlocal node_count
            node_key = str(kwargs.get("node_key") or "")
            try:
                result = self.graph_store.upsert_node(**kwargs)
            except Exception as exc:
                result = {"status": "failed", "error": str(exc)}
            if result.get("status") == "success":
                node_count += 1
            record(result, node_key)
            return node_key

        def upsert_edge(**kwargs: Any) -> None:
            nonlocal edge_count
            edge_key = str(
                kwargs.get("edge_key")
                or self.graph_store.edge_key(
                    str(kwargs.get("source_node_key") or ""),
                    str(kwargs.get("target_node_key") or ""),
                    str(kwargs.get("relation_type") or "RELATED_TO"),
                )
            )
            try:
                result = self.graph_store.upsert_edge(**kwargs)
            except Exception as exc:
                result = {"status": "failed", "error": str(exc)}
            if result.get("status") == "success":
                edge_count += 1
            record(result, edge_key)

        upsert_node(
            node_key=daily_key,
            node_type="daily_memory_graph",
            ref_type="daily_memory_graph",
            ref_id=int(graph_id) if graph_id else review_id,
            title=f"Daily Memory Graph {review_date}",
            content=str(daily_graph.get("summary") or ""),
            metadata={"review_id": review_id, "review_date": review_date},
            status="active",
        )

        for event in raw_events:
            event_id = event.get("id")
            if not event_id:
                continue
            node_key = self.graph_store.node_key("raw_event", int(event_id))
            upsert_node(
                node_key=node_key,
                node_type="raw_event",
                ref_type="raw_event",
                ref_id=int(event_id),
                title=f"Raw Event {event_id}",
                content=str(event.get("content") or ""),
                metadata={
                    "review_id": review_id,
                    "review_date": review_date,
                    "source_type": event.get("source_type") or "",
                    "role": event.get("role") or "",
                },
                status="active",
            )
            upsert_edge(
                source_node_key=node_key,
                target_node_key=daily_key,
                relation_type="PART_OF_DAILY_GRAPH",
                metadata={"review_id": review_id},
            )

        for memory in memories:
            memory_id = memory.get("id")
            if not memory_id:
                continue
            memory_type = str(memory.get("memory_type") or "memory")
            node_type = "semantic_memory" if memory_type == "semantic" else "episodic_memory"
            node_key = self.graph_store.node_key("memory", int(memory_id))
            upsert_node(
                node_key=node_key,
                node_type=node_type,
                ref_type="memory",
                ref_id=int(memory_id),
                title=str((memory.get("metadata") or {}).get("title") or memory_type),
                content=str(memory.get("content") or ""),
                metadata={
                    "review_id": review_id,
                    "review_date": review_date,
                    "memory_type": memory_type,
                    "merge_key": memory.get("merge_key") or "",
                },
                status=str(memory.get("status") or "active"),
            )
            upsert_edge(
                source_node_key=node_key,
                target_node_key=daily_key,
                relation_type="PART_OF_DAILY_GRAPH",
                metadata={"review_id": review_id},
            )
            for ref in memory.get("evidence_refs") or []:
                raw_event_id = self.raw_event_id_from_ref(ref)
                if raw_event_id is not None:
                    upsert_edge(
                        source_node_key=self.graph_store.node_key("raw_event", raw_event_id),
                        target_node_key=node_key,
                        relation_type="EVIDENCE_OF",
                        metadata={"review_id": review_id, "target_type": "memory"},
                    )

        for problem in problems:
            problem_id = problem.get("id")
            if not problem_id:
                continue
            node_key = self.graph_store.node_key("problem", int(problem_id))
            upsert_node(
                node_key=node_key,
                node_type="problem",
                ref_type="problem",
                ref_id=int(problem_id),
                title=str(problem.get("description") or f"Problem {problem_id}"),
                content=" | ".join(
                    [
                        str(problem.get("problem_type") or ""),
                        str(problem.get("subject") or ""),
                        str(problem.get("description") or ""),
                        str(problem.get("root_cause") or ""),
                    ]
                ),
                metadata={
                    "review_id": review_id,
                    "review_date": review_date,
                    "merge_key": problem.get("merge_key") or "",
                },
                status=str(problem.get("status") or "open"),
            )
            upsert_edge(
                source_node_key=node_key,
                target_node_key=daily_key,
                relation_type="PART_OF_DAILY_GRAPH",
                metadata={"review_id": review_id},
            )
            for ref in problem.get("evidence_refs") or []:
                raw_event_id = self.raw_event_id_from_ref(ref)
                if raw_event_id is not None:
                    upsert_edge(
                        source_node_key=self.graph_store.node_key("raw_event", raw_event_id),
                        target_node_key=node_key,
                        relation_type="EVIDENCE_OF",
                        metadata={"review_id": review_id, "target_type": "problem"},
                    )

        for node in daily_graph.get("nodes") or []:
            node_key = str(node.get("node_key") or node.get("node_id") or "")
            if not node_key:
                continue
            upsert_node(
                node_key=node_key,
                node_type=str(node.get("node_type") or "action"),
                ref_type=str(node.get("ref_type") or ""),
                ref_id=node.get("ref_id"),
                title=str(node.get("title") or node_key),
                content=str(node.get("content") or ""),
                metadata={
                    "review_id": review_id,
                    "review_date": review_date,
                    **dict(node.get("metadata") or {}),
                },
                status="active",
            )
            upsert_edge(
                source_node_key=node_key,
                target_node_key=daily_key,
                relation_type="PART_OF_DAILY_GRAPH",
                metadata={"review_id": review_id},
            )

        for edge in daily_graph.get("edges") or []:
            source = str(edge.get("source_node_key") or edge.get("source") or "")
            target = str(edge.get("target_node_key") or edge.get("target") or "")
            if not source or not target:
                continue
            upsert_edge(
                source_node_key=source,
                target_node_key=target,
                relation_type=str(edge.get("relation_type") or "RELATED_TO"),
                weight=float(edge.get("weight") or 1.0),
                metadata={
                    "review_id": review_id,
                    "review_date": review_date,
                    "evidence_event_ids": edge.get("evidence_event_ids") or edge.get("evidence") or [],
                    **dict(edge.get("metadata") or {}),
                },
            )

        return self._batch_status(
            backend=str(self.graph_store.get_status().get("backend") or "graph"),
            attempted=node_count + edge_count + len(errors),
            upserted=node_count + edge_count,
            skipped=0,
            results=results,
            errors=errors,
            extra={"nodes_upserted": node_count, "edges_upserted": edge_count},
        )

    def sync_evidence_edges(
        self,
        *,
        target_node_key: str,
        target_type: str,
        evidence_refs: list[Any],
    ) -> list[Dict[str, Any]]:
        if not self.settings.graph_sync_raw_events:
            return []
        results: list[Dict[str, Any]] = []
        for ref in evidence_refs:
            raw_event_id = self.raw_event_id_from_ref(ref)
            if raw_event_id is None:
                continue
            source_key = self.graph_store.node_key("raw_event", raw_event_id)
            self.graph_store.upsert_node(
                node_key=source_key,
                node_type="raw_event",
                ref_type="raw_event",
                ref_id=raw_event_id,
                title=f"Raw Event {raw_event_id}",
                content="",
                metadata={"source": "evidence_ref"},
            )
            results.append(
                self.graph_store.upsert_edge(
                    source_node_key=source_key,
                    target_node_key=target_node_key,
                    relation_type="EVIDENCE_OF",
                    weight=1.0,
                    metadata={"target_type": target_type},
                )
            )
        return results

    @staticmethod
    def raw_event_id_from_ref(ref: Any) -> Optional[int]:
        if isinstance(ref, int):
            return ref
        if isinstance(ref, str) and ref.isdigit():
            return int(ref)
        if isinstance(ref, dict):
            ref_type = str(ref.get("ref_type") or ref.get("source_type") or ref.get("type") or "")
            ref_id = ref.get("ref_id") or ref.get("source_id") or ref.get("id")
            if "raw_event" in ref_type and ref_id is not None:
                try:
                    return int(ref_id)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _batch_status(
        *,
        backend: str,
        attempted: int,
        upserted: int,
        skipped: int,
        results: list[Dict[str, Any]],
        errors: list[Dict[str, Any]],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if attempted == 0:
            status = "skipped"
        elif errors and upserted > 0:
            status = "partial"
        elif errors:
            status = "failed"
        else:
            status = "success"
        return {
            "backend": backend,
            "status": status,
            "attempted": attempted,
            "upserted": upserted,
            "skipped": skipped,
            "errors": errors,
            "results": results,
            **dict(extra or {}),
        }
