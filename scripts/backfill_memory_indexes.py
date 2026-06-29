from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaoyan_agent.core.settings import Settings, get_settings  # noqa: E402
from kaoyan_agent.db import database  # noqa: E402
from kaoyan_agent.db.database import get_connection, json_loads, rows_to_dicts  # noqa: E402
from kaoyan_agent.repositories.memory_repository import MemoryRepository  # noqa: E402
from kaoyan_agent.services.graph_store import GraphStore  # noqa: E402
from kaoyan_agent.services.vector_store import VectorStore  # noqa: E402


def backfill(
    *,
    vector: bool = False,
    graph: bool = False,
    all_indexes: bool = False,
    project_id: Optional[int] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    settings: Optional[Settings] = None,
    vector_store: Optional[VectorStore] = None,
    graph_store: Optional[GraphStore] = None,
) -> Dict[str, Any]:
    settings = settings or get_settings()
    do_vector = bool(all_indexes or vector)
    do_graph = bool(all_indexes or graph)
    if not do_vector and not do_graph:
        do_vector = True
        do_graph = True

    database.init_db()
    memories = MemoryRepository().list(limit=limit, project_id=project_id)
    problems = list_problem_rows(project_id=project_id, limit=limit)
    raw_events = list_table_rows("raw_events", project_id=project_id, limit=limit)
    mistake_cards = list_table_rows("mistake_cards", project_id=project_id, limit=limit)
    study_tasks = list_table_rows("study_tasks", project_id=project_id, limit=limit)
    focus_sessions = list_table_rows("focus_sessions", project_id=project_id, limit=limit)

    vector_store = vector_store or VectorStore(settings)
    graph_store = graph_store or GraphStore(settings)
    summary: Dict[str, Any] = {
        "dry_run": dry_run,
        "sqlite": {
            "memories": len(memories),
            "problem_board": len(problems),
            "raw_events": len(raw_events),
            "mistake_cards": len(mistake_cards),
            "study_tasks": len(study_tasks),
            "focus_sessions": len(focus_sessions),
        },
        "memory_count": len(memories),
        "problem_count": len(problems),
        "vector": {},
        "graph": {},
        "edges": {},
    }

    if do_vector:
        for memory in memories:
            result = {"status": "dry_run"} if dry_run else vector_store.upsert_memory(memory)
            add_status(summary["vector"], result)
        for problem in problems:
            result = {"status": "dry_run"} if dry_run else vector_store.upsert_problem(problem)
            add_status(summary["vector"], result)
        summary["vector_status"] = vector_store.get_status()

    if do_graph:
        graph_ops: list[Dict[str, Any]] = []
        graph_ops.extend(upsert_raw_events(graph_store, raw_events, dry_run=dry_run))
        graph_ops.extend(upsert_memories(graph_store, memories, dry_run=dry_run))
        graph_ops.extend(upsert_problems(graph_store, problems, dry_run=dry_run))
        graph_ops.extend(upsert_mistake_cards(graph_store, mistake_cards, dry_run=dry_run))
        graph_ops.extend(upsert_study_tasks(graph_store, study_tasks, dry_run=dry_run))
        graph_ops.extend(upsert_focus_sessions(graph_store, focus_sessions, dry_run=dry_run))
        for result in graph_ops:
            add_status(summary["graph"], result)
        for result in upsert_evidence_edges(graph_store, memories, problems, dry_run=dry_run):
            add_status(summary["edges"], result)
        for result in upsert_task_focus_edges(graph_store, study_tasks, focus_sessions, dry_run=dry_run):
            add_status(summary["edges"], result)
        summary["graph_status"] = graph_store.get_status()

    return summary


def add_status(bucket: Dict[str, int], result: Dict[str, Any]) -> None:
    status = str(result.get("status") or "unknown")
    bucket[status] = int(bucket.get(status, 0)) + 1


def list_table_rows(table: str, project_id: Optional[int] = None, limit: Optional[int] = None) -> list[dict]:
    if not table_exists(table):
        return []
    where = ""
    params: list[Any] = []
    if project_id is not None and table_has_column(table, "project_id"):
        where = "WHERE project_id = ?"
        params.append(project_id)
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(1, int(limit)))
    with closing(get_connection()) as connection:
        rows = connection.execute(
            f"SELECT * FROM {table} {where} ORDER BY id DESC {limit_clause}",
            tuple(params),
        ).fetchall()
    return rows_to_dicts(rows)


def list_problem_rows(project_id: Optional[int] = None, limit: Optional[int] = None) -> list[dict]:
    rows = list_table_rows("problem_board", project_id=project_id, limit=limit)
    for problem in rows:
        problem["evidence"] = json_loads(problem.get("evidence_json", "[]"), [])
        problem["evidence_refs"] = json_loads(problem.get("evidence_refs_json", "[]"), [])
        problem["embedding"] = json_loads(problem.get("embedding_json", "[]"), [])
    return rows


def table_exists(table: str) -> bool:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
    return bool(row)


def table_has_column(table: str, column: str) -> bool:
    with closing(get_connection()) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def upsert_raw_events(graph_store: GraphStore, raw_events: list[dict], dry_run: bool = False) -> list[Dict[str, Any]]:
    results = []
    for event in raw_events:
        event_id = int(event.get("id") or 0)
        result = {"status": "dry_run"} if dry_run else graph_store.upsert_node(
            node_key=graph_store.node_key("raw_event", event_id),
            node_type="raw_event",
            ref_type="raw_event",
            ref_id=event_id,
            title=f"{event.get('role') or 'event'} · {event.get('source_type') or 'raw'}",
            content=str(event.get("content") or ""),
            metadata={
                "project_id": event.get("project_id"),
                "session_id": event.get("session_id"),
                "source_type": event.get("source_type"),
                "source_id": event.get("source_id"),
                "created_at": event.get("created_at"),
            },
        )
        results.append(result)
    return results


def upsert_memories(graph_store: GraphStore, memories: list[dict], dry_run: bool = False) -> list[Dict[str, Any]]:
    return [
        {"status": "dry_run"} if dry_run else upsert_memory_node(graph_store, memory)
        for memory in memories
    ]


def upsert_problems(graph_store: GraphStore, problems: list[dict], dry_run: bool = False) -> list[Dict[str, Any]]:
    return [
        {"status": "dry_run"} if dry_run else upsert_problem_node(graph_store, problem)
        for problem in problems
    ]


def upsert_mistake_cards(graph_store: GraphStore, cards: list[dict], dry_run: bool = False) -> list[Dict[str, Any]]:
    results = []
    for card in cards:
        card_id = int(card.get("id") or 0)
        content = " | ".join(
            str(part)
            for part in (
                card.get("subject"),
                card.get("chapter"),
                card.get("question"),
                card.get("analysis"),
                card.get("mistake_reason"),
                card.get("knowledge_points"),
            )
            if str(part or "").strip()
        )
        result = {"status": "dry_run"} if dry_run else graph_store.upsert_node(
            node_key=graph_store.node_key("mistake_card", card_id),
            node_type="mistake_card",
            ref_type="mistake_card",
            ref_id=card_id,
            title=str(card.get("question") or f"MistakeCard {card_id}")[:80],
            content=content,
            metadata={
                "project_id": card.get("project_id"),
                "subject": card.get("subject"),
                "chapter": card.get("chapter"),
                "mistake_reason": card.get("mistake_reason"),
                "review_priority": card.get("review_priority"),
                "mastery_status": card.get("mastery_status"),
            },
            status=str(card.get("mastery_status") or "active"),
        )
        results.append(result)
    return results


def upsert_study_tasks(graph_store: GraphStore, tasks: list[dict], dry_run: bool = False) -> list[Dict[str, Any]]:
    results = []
    for task in tasks:
        task_id = int(task.get("id") or 0)
        result = {"status": "dry_run"} if dry_run else graph_store.upsert_node(
            node_key=graph_store.node_key("study_task", task_id),
            node_type="study_task",
            ref_type="study_task",
            ref_id=task_id,
            title=str(task.get("title") or f"StudyTask {task_id}"),
            content=str(task.get("reason") or ""),
            metadata={
                "project_id": task.get("project_id"),
                "subject": task.get("subject"),
                "estimated_minutes": task.get("estimated_minutes"),
                "source": task.get("source"),
                "related_problem_id": task.get("related_problem_id"),
                "scheduled_date": task.get("scheduled_date"),
                "status": task.get("status"),
            },
            status=str(task.get("status") or "active"),
        )
        results.append(result)
    return results


def upsert_focus_sessions(graph_store: GraphStore, sessions: list[dict], dry_run: bool = False) -> list[Dict[str, Any]]:
    results = []
    for session in sessions:
        session_id = int(session.get("id") or 0)
        result = {"status": "dry_run"} if dry_run else graph_store.upsert_node(
            node_key=graph_store.node_key("focus_session", session_id),
            node_type="focus_session",
            ref_type="focus_session",
            ref_id=session_id,
            title=str(session.get("task_title") or f"FocusSession {session_id}"),
            content=str(session.get("reflection") or ""),
            metadata={
                "project_id": session.get("project_id"),
                "task_id": session.get("task_id"),
                "subject": session.get("subject"),
                "timer_status": session.get("timer_status"),
                "actual_seconds": session.get("actual_seconds"),
                "completion_status": session.get("completion_status"),
            },
            status=str(session.get("timer_status") or "active"),
        )
        results.append(result)
    return results


def upsert_evidence_edges(
    graph_store: GraphStore,
    memories: list[dict],
    problems: list[dict],
    dry_run: bool = False,
) -> list[Dict[str, Any]]:
    results = []
    for memory in memories:
        memory_id = int(memory.get("id") or 0)
        for raw_event_id in raw_event_ids(memory.get("evidence_refs") or []):
            results.append(edge_or_dry_run(
                graph_store,
                graph_store.node_key("raw_event", raw_event_id),
                graph_store.node_key("memory", memory_id),
                "EVIDENCE_OF",
                dry_run=dry_run,
            ))
    for problem in problems:
        problem_id = int(problem.get("id") or 0)
        for raw_event_id in raw_event_ids(problem.get("evidence_refs") or []):
            results.append(edge_or_dry_run(
                graph_store,
                graph_store.node_key("raw_event", raw_event_id),
                graph_store.node_key("problem", problem_id),
                "EVIDENCE_OF",
                dry_run=dry_run,
            ))
    return results


def upsert_task_focus_edges(
    graph_store: GraphStore,
    tasks: list[dict],
    sessions: list[dict],
    dry_run: bool = False,
) -> list[Dict[str, Any]]:
    results = []
    for task in tasks:
        related_problem_id = task.get("related_problem_id")
        if related_problem_id:
            results.append(edge_or_dry_run(
                graph_store,
                graph_store.node_key("problem", int(related_problem_id)),
                graph_store.node_key("study_task", int(task.get("id") or 0)),
                "SUGGESTS",
                dry_run=dry_run,
            ))
    for session in sessions:
        task_id = session.get("task_id")
        if task_id:
            results.append(edge_or_dry_run(
                graph_store,
                graph_store.node_key("study_task", int(task_id)),
                graph_store.node_key("focus_session", int(session.get("id") or 0)),
                "CREATED_FROM",
                dry_run=dry_run,
            ))
    return results


def edge_or_dry_run(
    graph_store: GraphStore,
    source_node_key: str,
    target_node_key: str,
    relation_type: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if dry_run:
        return {"status": "dry_run"}
    return graph_store.upsert_edge(
        source_node_key=source_node_key,
        target_node_key=target_node_key,
        relation_type=relation_type,
    )


def upsert_memory_node(graph_store: GraphStore, memory: Dict[str, Any]) -> Dict[str, Any]:
    memory_id = int(memory.get("id") or 0)
    return graph_store.upsert_node(
        node_key=graph_store.node_key("memory", memory_id),
        node_type="memory",
        ref_type="memory",
        ref_id=memory_id,
        title=str(memory.get("memory_type") or f"Memory {memory_id}"),
        content=str(memory.get("content") or ""),
        metadata={
            "project_id": memory.get("project_id"),
            "review_id": memory.get("review_id"),
            "merge_key": memory.get("merge_key") or "",
            "status": memory.get("status") or "active",
        },
        embedding=memory.get("embedding") or [],
        status=str(memory.get("status") or "active"),
    )


def upsert_problem_node(graph_store: GraphStore, problem: Dict[str, Any]) -> Dict[str, Any]:
    problem_id = int(problem.get("id") or 0)
    return graph_store.upsert_node(
        node_key=graph_store.node_key("problem", problem_id),
        node_type="problem",
        ref_type="problem",
        ref_id=problem_id,
        title=str(problem.get("description") or f"Problem {problem_id}")[:120],
        content=problem_content(problem),
        metadata={
            "project_id": problem.get("project_id"),
            "review_id": problem.get("review_id"),
            "merge_key": problem.get("merge_key") or "",
            "status": problem.get("status") or "open",
            "subject": problem.get("subject") or "",
            "problem_type": problem.get("problem_type") or "",
        },
        embedding=problem.get("embedding") or [],
        status=str(problem.get("status") or "open"),
    )


def raw_event_ids(evidence_refs: list[Any]) -> list[int]:
    ids: list[int] = []
    for ref in evidence_refs:
        raw_id = raw_event_id_from_ref(ref)
        if raw_id is not None and raw_id not in ids:
            ids.append(raw_id)
    return ids


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


def problem_content(problem: Dict[str, Any]) -> str:
    parts: Iterable[Any] = (
        problem.get("problem_type") or "",
        problem.get("subject") or "",
        problem.get("description") or "",
        problem.get("root_cause") or "",
        problem.get("suggested_action") or "",
    )
    return " | ".join(str(part) for part in parts if str(part).strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Chroma and Neo4j memory indexes.")
    parser.add_argument("--vector", action="store_true", help="Backfill Chroma vector index.")
    parser.add_argument("--graph", action="store_true", help="Backfill Neo4j graph index.")
    parser.add_argument("--all", dest="all_indexes", action="store_true", help="Backfill all indexes.")
    parser.add_argument("--project-id", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = backfill(
        vector=args.vector,
        graph=args.graph,
        all_indexes=args.all_indexes,
        project_id=args.project_id,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

