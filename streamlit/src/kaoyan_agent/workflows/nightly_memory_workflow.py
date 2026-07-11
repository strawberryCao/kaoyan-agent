from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryAgent
from kaoyan_agent.agents.problem_discovery_agent import ProblemDiscoveryAgent
from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.memory.gates import GateDecision, MemoryGateEngine
from kaoyan_agent.repositories.agent_runs import AgentRunRepository
from kaoyan_agent.repositories.graphs import DailyMemoryGraphRepository, GlobalGraphRepository
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.nightly_review_repository import NightlyReviewRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository
from kaoyan_agent.repositories.skill_memory_repository import SkillMemoryRepository
from kaoyan_agent.schemas.contracts import NightlyWorkflowResult
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.services.memory_index_service import MemoryIndexService
from kaoyan_agent.services.focus_temporal_tracker import DETECTOR_VERSION


def today_str() -> str:
    return datetime.now().astimezone().date().isoformat()


def filter_reliable_focus_evidence(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep legacy rows in SQLite while preventing them from driving new memories."""

    filtered: list[Dict[str, Any]] = []
    for event in raw_events:
        source_type = str(event.get("source_type") or "")
        metadata = event.get("metadata") or {}
        if source_type == "focus_state_event":
            recognition_source = str(metadata.get("recognition_source") or "")
            version = str(metadata.get("detector_version") or "")
            if recognition_source == "local_yolo" and version != DETECTOR_VERSION:
                continue
            if recognition_source != "manual" and str(metadata.get("evidence_status") or "") != "sufficient":
                continue
        if source_type == "focus_report":
            version = str(metadata.get("detector_version") or "")
            evidence_status = str(metadata.get("evidence_status") or "")
            if version != DETECTOR_VERSION or evidence_status != "sufficient":
                continue
        filtered.append(event)
    return filtered


class NightlyMemoryWorkflow:
    """Formal nightly chain: evidence -> structured extraction -> SQLite -> indexes."""

    workflow_name = "nightly_memory"

    def __init__(
        self,
        settings: Settings | None = None,
        nightly_repository: NightlyReviewRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
        memory_repository: MemoryRepository | None = None,
        problem_repository: ProblemRepository | None = None,
        graph_repository: DailyMemoryGraphRepository | None = None,
        global_graph_repository: GlobalGraphRepository | None = None,
        skill_repository: SkillMemoryRepository | None = None,
        gate_engine: MemoryGateEngine | None = None,
        agent_run_repository: AgentRunRepository | None = None,
        memory_index_service: MemoryIndexService | None = None,
        problem_discovery_agent: ProblemDiscoveryAgent | None = None,
    ):
        self.settings = settings or get_settings()
        self.nightly_repository = nightly_repository or NightlyReviewRepository()
        self.raw_event_repository = raw_event_repository or RawEventRepository()
        self.memory_repository = memory_repository or MemoryRepository()
        self.problem_repository = problem_repository or ProblemRepository()
        self.graph_repository = graph_repository or DailyMemoryGraphRepository()
        self.global_graph_repository = global_graph_repository or GlobalGraphRepository()
        self.skill_repository = skill_repository or SkillMemoryRepository()
        self.gate_engine = gate_engine or MemoryGateEngine()
        self.agent_run_repository = agent_run_repository or AgentRunRepository()
        self.memory_index_service = memory_index_service or MemoryIndexService(self.settings)
        self.problem_discovery_agent = problem_discovery_agent or ProblemDiscoveryAgent(self.settings)

    def run(
        self,
        review_date: str | None = None,
        project_id: Optional[int] = None,
    ) -> NightlyWorkflowResult:
        return self.run_for_project(project_id=project_id, review_date=review_date)

    def run_for_project(
        self,
        project_id: Optional[int],
        review_date: str | None = None,
    ) -> NightlyWorkflowResult:
        review_date = review_date or today_str()

        sessions = self.nightly_repository.list_sessions_by_date(review_date, project_id=project_id)
        conversations = self.nightly_repository.list_conversations_by_date(review_date, project_id=project_id)
        raw_events = filter_reliable_focus_evidence(
            self.raw_event_repository.list_by_project_and_date(
                project_id=project_id,
                date_str=review_date,
            )
        )
        focus_sessions = self.nightly_repository.list_focus_sessions_by_date(review_date, project_id=project_id)
        mistake_cards = self.nightly_repository.list_mistake_cards_by_date(review_date, project_id=project_id)
        study_tasks = self.nightly_repository.list_study_tasks_by_date(review_date, project_id=project_id)
        memories = self.memory_repository.list(project_id=project_id)
        open_problems = self.problem_repository.list_open(project_id=project_id)
        skill_memories = self.skill_repository.list(limit=100)
        recent_daily_graphs = self.graph_repository.list_recent(limit=5)
        global_graph_nodes = self.global_graph_repository.list_nodes(limit=120)
        global_graph_edges = self.global_graph_repository.list_edges(limit=240)

        agent_result = NightlyMemoryAgent(self.settings).run(
            review_date=review_date,
            sessions=sessions,
            conversations=conversations,
            raw_events=raw_events,
            memories=memories,
            open_problems=open_problems,
            skill_memories=skill_memories,
            recent_daily_graphs=recent_daily_graphs,
            global_graph_nodes=global_graph_nodes,
            global_graph_edges=global_graph_edges,
            focus_sessions=focus_sessions,
            mistake_cards=mistake_cards,
            study_tasks=study_tasks,
        )
        output = agent_result.output
        result = output.model_dump()
        result["validation_errors"] = agent_result.validation_errors
        result["normalization_diagnostics"] = agent_result.normalization_diagnostics
        result["candidate_results"] = agent_result.candidate_results

        review_id = self.nightly_repository.create(
            review_date=review_date,
            result=result,
            raw_response=agent_result.raw_response,
            parse_status=agent_result.parse_status,
            error_message=agent_result.error_message,
            validation_errors=agent_result.validation_errors,
            normalization_diagnostics=agent_result.normalization_diagnostics,
            candidate_results=agent_result.candidate_results,
            index_sync_status=self.empty_index_sync_status(agent_result.parse_status),
            inserted_counts={},
            project_id=project_id,
        )

        inserted_memory_ids: list[int] = []
        inserted_problem_ids: list[int] = []
        inserted_skill_ids: list[int] = []
        gate_results: list[dict[str, Any]] = []
        daily_memory_graph_id: int | None = None
        index_sync_status = self.empty_index_sync_status(agent_result.parse_status)
        inserted_counts: dict[str, Any] = {}
        persisted_memories: list[dict[str, Any]] = []
        persisted_problems: list[dict[str, Any]] = []
        daily_graph: dict[str, Any] = {}

        if agent_result.parse_status == "success":
            extracted_memory_ids, extracted_memories = self.save_extracted_memories(
                output=output,
                review_id=review_id,
                review_date=review_date,
                project_id=project_id,
            )
            inserted_memory_ids.extend(extracted_memory_ids)
            persisted_memories.extend(extracted_memories)

            legacy_memory_ids, memory_gate_results = self.save_memories(
                memories=result.get("memory_updates", []),
                review_id=review_id,
                project_id=project_id,
                daily_graph_key=None,
                existing_memories=memories + persisted_memories,
            )
            inserted_memory_ids.extend(legacy_memory_ids)
            gate_results.extend(memory_gate_results)
            persisted_memories.extend(self.persisted_from_gate(memory_gate_results, "memory", project_id, review_id))

            daily_memory_graph_id = self.save_daily_memory_graph(
                review_date=review_date,
                review_id=review_id,
                output=output,
                raw_events=raw_events,
                persisted_memories=persisted_memories,
            )
            daily_graph = self.graph_repository.get(daily_memory_graph_id) or {}
            daily_graph_key = f"daily_memory_graph:{daily_memory_graph_id}"
            self.merge_daily_graph_to_global(daily_graph, review_id=review_id, review_date=review_date)

            chroma_context = self.retrieve_graph_discovery_context(review_date, project_id)
            neo4j_neighbors = self.collect_graph_neighbors(persisted_memories, [])
            discovery_result = self.problem_discovery_agent.discover_from_graph(
                review_date=review_date,
                daily_graph=daily_graph,
                recent_daily_graphs=recent_daily_graphs,
                global_graph_nodes=global_graph_nodes,
                global_graph_edges=global_graph_edges,
                chroma_results=chroma_context,
                neo4j_neighbors=neo4j_neighbors,
                candidate_problems=result.get("candidate_problems") or result.get("discovered_problems") or [],
                raw_events=raw_events,
                memories=memories + persisted_memories,
                open_problems=open_problems,
            )
            result["problem_discovery"] = {
                "parse_status": discovery_result.parse_status,
                "error_message": discovery_result.error_message,
                "source": "graph_context",
            }

            problem_ids, problem_gate_results = self.save_problems(
                problems=discovery_result.problems,
                review_id=review_id,
                project_id=project_id,
                daily_graph_key=daily_graph_key,
                existing_problems=open_problems,
            )
            inserted_problem_ids.extend(problem_ids)
            gate_results.extend(problem_gate_results)
            persisted_problems.extend(self.persisted_from_gate(problem_gate_results, "problem", project_id, review_id))

            skill_ids, skill_gate_results = self.save_skills(
                skills=result.get("skill_observations") or result.get("skill_updates") or [],
                review_id=review_id,
                daily_graph_key=daily_graph_key,
                existing_skills=skill_memories,
            )
            inserted_skill_ids.extend(skill_ids)
            gate_results.extend(skill_gate_results)

            index_sync_status = self.sync_indexes(
                review_id=review_id,
                review_date=review_date,
                daily_graph=daily_graph,
                raw_events=raw_events,
                memories=persisted_memories,
                problems=persisted_problems,
            )
            inserted_counts = {
                "episodic_memories": sum(
                    1
                    for memory in persisted_memories
                    if memory.get("memory_type") == "episodic" and memory.get("id") in inserted_memory_ids
                ),
                "semantic_memories": sum(
                    1
                    for memory in persisted_memories
                    if memory.get("memory_type") == "semantic" and memory.get("id") in inserted_memory_ids
                ),
                "legacy_memory_updates": sum(1 for item in memory_gate_results if item.get("operation") == "insert"),
                "problems": len([item for item in persisted_problems if item.get("id") in inserted_problem_ids]),
                "skills": len(inserted_skill_ids),
                "daily_graph_nodes": int(daily_graph.get("node_count") or len(daily_graph.get("nodes") or [])),
                "daily_graph_edges": int(daily_graph.get("edge_count") or len(daily_graph.get("edges") or [])),
            }
        else:
            index_sync_status = self.empty_index_sync_status(
                agent_result.parse_status,
                reason="parse_status is not success; long-term writes skipped",
            )
            inserted_counts = {
                "episodic_memories": 0,
                "semantic_memories": 0,
                "legacy_memory_updates": 0,
                "problems": 0,
                "skills": 0,
                "daily_graph_nodes": 0,
                "daily_graph_edges": 0,
            }

        result["gate_results"] = gate_results
        result["index_sync_status"] = index_sync_status
        result["inserted_counts"] = inserted_counts
        self.nightly_repository.update_chain_status(
            review_id=review_id,
            raw_result=result,
            gate_results=gate_results,
            index_sync_status=index_sync_status,
            inserted_counts=inserted_counts,
            validation_errors=agent_result.validation_errors,
            normalization_diagnostics=agent_result.normalization_diagnostics,
            candidate_results=agent_result.candidate_results,
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
                "focus_sessions_count": len(focus_sessions),
                "mistake_cards_count": len(mistake_cards),
                "study_tasks_count": len(study_tasks),
                "memories_count": len(memories),
                "open_problems_count": len(open_problems),
                "skill_memories_count": len(skill_memories),
                "recent_daily_graphs_count": len(recent_daily_graphs),
                "global_graph_nodes_count": len(global_graph_nodes),
                "global_graph_edges_count": len(global_graph_edges),
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
            inserted_skill_ids=inserted_skill_ids,
            daily_memory_graph_id=daily_memory_graph_id,
            gate_results=gate_results,
            error_message=agent_result.error_message,
            result=output,
            validation_errors=agent_result.validation_errors,
            normalization_diagnostics=agent_result.normalization_diagnostics,
            candidate_results=agent_result.candidate_results,
        )

    def save_extracted_memories(
        self,
        *,
        output: NightlyMemoryUpdateOutput,
        review_id: int,
        review_date: str,
        project_id: Optional[int],
    ) -> tuple[list[int], list[dict[str, Any]]]:
        inserted_ids: list[int] = []
        persisted: list[dict[str, Any]] = []

        for memory_type, values in (
            ("episodic", output.episodic_memories),
            ("semantic", output.semantic_memories),
        ):
            for index, value in enumerate(values, start=1):
                item = value.model_dump() if hasattr(value, "model_dump") else dict(value)
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                evidence_event_ids = item.get("evidence_event_ids") or item.get("source_event_ids") or []
                evidence_refs = item.get("evidence_refs") or [
                    {"source_type": "raw_event", "source_id": event_id, "quote": "", "note": ""}
                    for event_id in evidence_event_ids
                ]
                merge_key = str(item.get("merge_key") or "").strip()
                if not merge_key:
                    effective_date = item.get("event_date") or item.get("occurred_at") or review_date
                    merge_key = self.stable_merge_key(
                        "memory",
                        memory_type,
                        effective_date if memory_type == "episodic" else item.get("category") or "",
                        item.get("title") or "",
                        content,
                    )
                existing = self.memory_repository.find_by_merge_key(merge_key, project_id=project_id)
                row = {
                    "operation": "insert",
                    "memory_type": memory_type,
                    "content": content,
                    "importance": int(item.get("importance") or 3),
                    "confidence": float(item.get("confidence") or 0.5),
                    "merge_key": merge_key,
                    "reason": "nightly structured extraction",
                    "status": "active",
                    "valid_from": item.get("event_date") or item.get("occurred_at") or review_date,
                    "subject": item.get("subject") or item.get("category") or "",
                    "evidence_refs": evidence_refs,
                    "metadata": {
                        "title": item.get("title") or "",
                        "event_date": item.get("event_date") or item.get("occurred_at") or review_date,
                        "category": item.get("category") or "",
                        "evidence_event_ids": evidence_event_ids,
                        "source": "nightly_review",
                        "review_id": review_id,
                        "candidate_index": index,
                    },
                }
                if existing:
                    memory_id = int(existing["id"])
                    self.memory_repository.update(memory_id, {**row, "operation": "merge"}, review_id=review_id)
                else:
                    memory_id = self.memory_repository.create(row, review_id=review_id, project_id=project_id)
                    inserted_ids.append(memory_id)
                persisted.append({**row, "id": memory_id, "project_id": project_id, "review_id": review_id})
                self.memory_repository.record_operation(
                    operation="merge" if existing else "insert",
                    candidate=row,
                    review_id=review_id,
                    memory_id=memory_id,
                    reason="nightly structured extraction",
                )
        return inserted_ids, persisted

    def save_memories(
        self,
        memories: List[Any],
        review_id: int,
        project_id: Optional[int],
        daily_graph_key: Optional[str],
        existing_memories: List[Dict[str, Any]],
    ) -> tuple[list[int], list[dict[str, Any]]]:
        inserted_ids: list[int] = []
        gate_results: list[dict[str, Any]] = []
        existing = list(existing_memories)
        for index, memory in enumerate(memories):
            if not isinstance(memory, dict):
                continue
            exact_match = self.memory_repository.find_by_merge_key(
                str(memory.get("merge_key") or ""),
                project_id=project_id,
            )
            decision = self.gate_engine.decide_memory(memory, existing, exact_match)
            memory_id = self.apply_memory_decision(
                decision=decision,
                review_id=review_id,
                project_id=project_id,
                daily_graph_key=daily_graph_key,
            )
            gate_record = decision.to_record("memory")
            self.enrich_gate_record(gate_record, memory, index)
            gate_record["persisted_id"] = memory_id
            gate_results.append(gate_record)
            if memory_id:
                if decision.operation == "insert":
                    inserted_ids.append(memory_id)
                existing.append({**decision.candidate, "id": memory_id})
        return inserted_ids, gate_results

    def apply_memory_decision(
        self,
        decision: GateDecision,
        review_id: int,
        project_id: Optional[int],
        daily_graph_key: Optional[str],
    ) -> Optional[int]:
        if decision.operation == "skip":
            self.memory_repository.record_operation(
                operation="skip",
                candidate=decision.candidate,
                review_id=review_id,
                reason=decision.reason,
            )
            return None

        memory_id = decision.target_id
        if memory_id and decision.operation in {"update", "merge"}:
            updated = self.memory_repository.update(
                memory_id,
                {**decision.candidate, "operation": decision.operation},
                review_id=review_id,
            )
            if not updated:
                memory_id = None
        if not memory_id:
            memory_id = self.memory_repository.create(
                {**decision.candidate, "operation": "insert"},
                review_id=review_id,
                project_id=project_id,
            )

        self.memory_repository.record_operation(
            operation=decision.operation,
            candidate=decision.candidate,
            review_id=review_id,
            memory_id=memory_id,
            reason=decision.reason,
        )
        if memory_id:
            self.upsert_global_target_node(
                target_type="memory",
                target_id=memory_id,
                title=str(decision.candidate.get("memory_type") or f"Memory {memory_id}"),
                content=str(decision.candidate.get("content") or ""),
                metadata={
                    "review_id": review_id,
                    "operation": decision.operation,
                    "merge_key": decision.candidate.get("merge_key") or "",
                    "evidence_refs": decision.candidate.get("evidence_refs") or [],
                },
                daily_graph_key=daily_graph_key,
                relation_type="PART_OF_DAILY_GRAPH",
                node_type="memory",
            )
        return memory_id

    def save_problems(
        self,
        problems: List[Any],
        review_id: int,
        project_id: Optional[int],
        daily_graph_key: Optional[str],
        existing_problems: List[Dict[str, Any]],
    ) -> tuple[list[int], list[dict[str, Any]]]:
        inserted_ids: list[int] = []
        gate_results: list[dict[str, Any]] = []
        existing = list(existing_problems)
        for index, problem in enumerate(problems):
            if not isinstance(problem, dict):
                continue
            exact_match = self.problem_repository.find_by_merge_key(
                str(problem.get("merge_key") or ""),
                project_id=project_id,
            )
            decision = self.gate_engine.decide_problem(problem, existing, exact_match)
            problem_id = self.apply_problem_decision(
                decision=decision,
                review_id=review_id,
                project_id=project_id,
                daily_graph_key=daily_graph_key,
            )
            gate_record = decision.to_record("problem")
            self.enrich_gate_record(gate_record, problem, index)
            gate_record["persisted_id"] = problem_id
            gate_results.append(gate_record)
            if problem_id:
                if decision.operation == "insert":
                    inserted_ids.append(problem_id)
                existing.append({**decision.candidate, "id": problem_id})
        return inserted_ids, gate_results

    def apply_problem_decision(
        self,
        decision: GateDecision,
        review_id: int,
        project_id: Optional[int],
        daily_graph_key: Optional[str],
    ) -> Optional[int]:
        if decision.operation == "skip":
            self.problem_repository.record_operation(
                operation="skip",
                candidate=decision.candidate,
                review_id=review_id,
                reason=decision.reason,
            )
            return None

        problem_id = decision.target_id
        if problem_id and decision.operation in {"update", "merge"}:
            updated = self.problem_repository.update(
                problem_id,
                {**decision.candidate, "operation": decision.operation},
                review_id=review_id,
            )
            if not updated:
                problem_id = None
        if not problem_id:
            problem_id = self.problem_repository.create(
                {**decision.candidate, "operation": "insert"},
                review_id=review_id,
                project_id=project_id,
            )

        self.problem_repository.record_operation(
            operation=decision.operation,
            candidate=decision.candidate,
            review_id=review_id,
            problem_id=problem_id,
            reason=decision.reason,
        )
        if problem_id:
            self.upsert_global_target_node(
                target_type="problem",
                target_id=problem_id,
                title=str(decision.candidate.get("description") or f"Problem {problem_id}"),
                content=self.problem_content(decision.candidate),
                metadata={
                    "review_id": review_id,
                    "operation": decision.operation,
                    "merge_key": decision.candidate.get("merge_key") or "",
                    "evidence_refs": decision.candidate.get("evidence_refs") or [],
                },
                daily_graph_key=daily_graph_key,
                relation_type="PART_OF_DAILY_GRAPH",
                node_type="problem",
            )
        return problem_id

    def save_skills(
        self,
        skills: List[Any],
        review_id: int,
        daily_graph_key: Optional[str],
        existing_skills: List[Dict[str, Any]],
    ) -> tuple[list[int], list[dict[str, Any]]]:
        inserted_ids: list[int] = []
        gate_results: list[dict[str, Any]] = []
        existing = list(existing_skills)
        for index, skill in enumerate(skills):
            if not isinstance(skill, dict):
                continue
            exact_match = self.skill_repository.find_by_key(
                merge_key=str(skill.get("merge_key") or ""),
                skill_name=str(skill.get("skill_name") or ""),
            )
            decision = self.gate_engine.decide_skill(skill, existing, exact_match)
            skill_id = self.apply_skill_decision(
                decision=decision,
                review_id=review_id,
                daily_graph_key=daily_graph_key,
            )
            gate_record = decision.to_record("skill")
            self.enrich_gate_record(gate_record, skill, index)
            gate_record["persisted_id"] = skill_id
            gate_results.append(gate_record)
            if skill_id:
                if decision.operation == "insert":
                    inserted_ids.append(skill_id)
                existing.append({**decision.candidate, "id": skill_id})
        return inserted_ids, gate_results

    def apply_skill_decision(
        self,
        decision: GateDecision,
        review_id: int,
        daily_graph_key: Optional[str],
    ) -> Optional[int]:
        if decision.operation == "skip":
            self.skill_repository.record_operation(
                operation="skip",
                candidate=decision.candidate,
                review_id=review_id,
                reason=decision.reason,
            )
            return None

        skill_id = decision.target_id
        if skill_id and decision.operation in {"update", "merge"}:
            updated = self.skill_repository.update(
                skill_id,
                {**decision.candidate, "operation": decision.operation},
                review_id=review_id,
            )
            if not updated:
                skill_id = None
        if not skill_id:
            skill_id = self.skill_repository.create(
                {**decision.candidate, "operation": "insert"},
                review_id=review_id,
            )

        self.skill_repository.record_operation(
            operation=decision.operation,
            candidate=decision.candidate,
            review_id=review_id,
            skill_id=skill_id,
            reason=decision.reason,
        )
        if skill_id:
            self.upsert_global_target_node(
                target_type="skill",
                target_id=skill_id,
                title=str(decision.candidate.get("skill_name") or f"Skill {skill_id}"),
                content=str(decision.candidate.get("description") or ""),
                metadata={
                    "review_id": review_id,
                    "operation": decision.operation,
                    "merge_key": decision.candidate.get("merge_key") or "",
                    "evidence_refs": decision.candidate.get("evidence_refs") or [],
                },
                daily_graph_key=daily_graph_key,
                relation_type="PART_OF_DAILY_GRAPH",
                node_type="skill",
            )
        return skill_id

    def save_daily_memory_graph(
        self,
        review_date: str,
        review_id: int,
        output: NightlyMemoryUpdateOutput,
        raw_events: List[Dict[str, Any]],
        persisted_memories: List[Dict[str, Any]],
    ) -> int:
        result = output.model_dump()
        legacy_graph = result.get("daily_memory_graph") or {}
        nodes = list(result.get("daily_graph_nodes") or legacy_graph.get("nodes") or [])
        edges = list(result.get("daily_graph_edges") or legacy_graph.get("edges") or [])
        nodes = [self.normalize_daily_node(node) for node in nodes if isinstance(node, dict)]
        edges = [self.normalize_daily_edge(edge) for edge in edges if isinstance(edge, dict)]

        existing_keys = {str(node.get("node_key") or "") for node in nodes}
        for event in raw_events:
            node_key = f"raw_event:{event['id']}"
            if node_key in existing_keys:
                continue
            nodes.append(
                {
                    "node_key": node_key,
                    "node_type": "raw_event",
                    "ref_type": "raw_event",
                    "ref_id": event["id"],
                    "title": f"Raw Event {event['id']}",
                    "content": event.get("content", ""),
                    "confidence": 1.0,
                    "metadata": {
                        "source_type": event.get("source_type", ""),
                        "role": event.get("role", ""),
                        "created_at": event.get("created_at", ""),
                    },
                }
            )
            existing_keys.add(node_key)

        for memory in persisted_memories:
            memory_id = memory.get("id")
            if not memory_id:
                continue
            node_key = f"memory:{memory_id}"
            if node_key not in existing_keys:
                nodes.append(
                    {
                        "node_key": node_key,
                        "node_type": "semantic_memory"
                        if memory.get("memory_type") == "semantic"
                        else "episodic_memory",
                        "ref_type": "memory",
                        "ref_id": int(memory_id),
                        "title": str((memory.get("metadata") or {}).get("title") or memory.get("memory_type") or ""),
                        "content": str(memory.get("content") or ""),
                        "confidence": float(memory.get("confidence") or 0.0),
                        "metadata": {"review_id": review_id, "memory_type": memory.get("memory_type") or ""},
                    }
                )
                existing_keys.add(node_key)
            for ref in memory.get("evidence_refs") or []:
                source_id = MemoryIndexService.raw_event_id_from_ref(ref)
                if source_id is not None:
                    edges.append(
                        {
                            "source_node_key": f"raw_event:{source_id}",
                            "target_node_key": node_key,
                            "relation_type": "EVIDENCE_OF",
                            "weight": 1.0,
                            "evidence_event_ids": [source_id],
                            "metadata": {"review_id": review_id},
                        }
                    )

        self.append_candidate_nodes(nodes, "problem", result.get("candidate_problems") or result.get("discovered_problems") or [])
        self.append_candidate_nodes(nodes, "action", result.get("next_actions", []))

        return self.graph_repository.create(
            graph_date=review_date,
            nodes=nodes,
            edges=edges,
            summary=str(legacy_graph.get("summary") or result.get("daily_summary") or ""),
            source_event_ids=[int(event["id"]) for event in raw_events],
            review_id=review_id,
            metadata={
                "review_id": review_id,
                "source": "nightly_review",
                "candidate_problem_count": len(result.get("candidate_problems") or result.get("discovered_problems") or []),
            },
        )

    def merge_daily_graph_to_global(
        self,
        daily_graph: Dict[str, Any],
        *,
        review_id: int,
        review_date: str,
    ) -> None:
        if not daily_graph:
            return
        daily_key = f"daily_memory_graph:{daily_graph.get('id') or review_id}"
        self.global_graph_repository.upsert_node(
            node_key=daily_key,
            node_type="daily_memory_graph",
            ref_type="daily_memory_graph",
            ref_id=daily_graph.get("id") or review_id,
            title=f"Daily Memory Graph {review_date}",
            content=str(daily_graph.get("summary") or ""),
            confidence=1.0,
            metadata={"review_id": review_id, "review_date": review_date},
        )
        for node in daily_graph.get("nodes") or []:
            node_key = str(node.get("node_key") or node.get("node_id") or "")
            if not node_key:
                continue
            self.global_graph_repository.upsert_node(
                node_key=node_key,
                node_type=str(node.get("node_type") or "other"),
                ref_type=str(node.get("ref_type") or ""),
                ref_id=node.get("ref_id"),
                title=str(node.get("title") or node_key),
                content=str(node.get("content") or ""),
                confidence=float(node.get("confidence") or 0.0),
                metadata={"review_id": review_id, "review_date": review_date, **dict(node.get("metadata") or {})},
            )
            self.global_graph_repository.upsert_edge(
                source_node_key=node_key,
                target_node_key=daily_key,
                relation_type="PART_OF_DAILY_GRAPH",
                metadata={"review_id": review_id, "review_date": review_date},
            )
        for edge in daily_graph.get("edges") or []:
            source = str(edge.get("source_node_key") or edge.get("source") or "")
            target = str(edge.get("target_node_key") or edge.get("target") or "")
            if not source or not target:
                continue
            self.global_graph_repository.upsert_edge(
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

    def sync_indexes(
        self,
        *,
        review_id: int,
        review_date: str,
        daily_graph: Dict[str, Any],
        raw_events: List[Dict[str, Any]],
        memories: List[Dict[str, Any]],
        problems: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            vector_status = self.memory_index_service.sync_nightly_memories_to_chroma(
                memories,
                review_id=review_id,
                review_date=review_date,
            )
        except Exception as exc:
            vector_status = {"status": "failed", "errors": [{"error": str(exc)}], "result": {}}
        for problem in problems:
            try:
                problem_result = self.memory_index_service.vector_store.upsert_problem(
                    problem,
                    metadata={"date": review_date, "source": "nightly_review", "review_id": review_id},
                )
            except Exception as exc:
                problem_result = {"status": "failed", "error": str(exc)}
            vector_status.setdefault("problem_results", []).append(problem_result)
            vector_status["attempted"] = int(vector_status.get("attempted") or 0) + 1
            if problem_result.get("status") == "success":
                vector_status["upserted"] = int(vector_status.get("upserted") or 0) + 1
            elif problem_result.get("status") == "skipped":
                vector_status["skipped"] = int(vector_status.get("skipped") or 0) + 1
            else:
                vector_status.setdefault("errors", []).append(
                    {
                        "problem_id": problem.get("id"),
                        "status": problem_result.get("status") or "",
                        "error": problem_result.get("error") or problem_result.get("reason") or "",
                    }
                )
        vector_status["status"] = self.aggregate_sync_status(vector_status)

        try:
            graph_status = self.memory_index_service.sync_daily_graph_to_neo4j(
                daily_graph=daily_graph,
                raw_events=raw_events,
                memories=memories,
                problems=problems,
                review_id=review_id,
                review_date=review_date,
            )
        except Exception as exc:
            graph_status = {"status": "failed", "errors": [{"error": str(exc)}], "result": {}}

        return {
            "vector": vector_status,
            "graph": graph_status,
        }

    def retrieve_graph_discovery_context(
        self,
        review_date: str,
        project_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        try:
            status = self.memory_index_service.vector_store.get_status()
            if not status.get("available"):
                return [
                    {
                        "retrieval_backend": "chroma",
                        "vector_used": False,
                        "fallback_reason": status.get("error") or status.get("embedding_error") or "Chroma unavailable",
                    }
                ]
            return self.memory_index_service.vector_store.query(
                f"{review_date} 学习问题 复盘 计划 专注 错题",
                limit=8,
                project_id=project_id,
            )
        except Exception as exc:
            return [{"retrieval_error": str(exc), "retrieval_backend": "unavailable"}]

    def collect_graph_neighbors(
        self,
        memories: List[Dict[str, Any]],
        problems: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        neighbors: list[dict[str, Any]] = []
        for item_type, values in (("memory", memories), ("problem", problems)):
            for value in values:
                item_id = value.get("id")
                if not item_id:
                    continue
                try:
                    neighbors.append(
                        {
                            "source_type": item_type,
                            "source_id": item_id,
                            "neighbors": self.memory_index_service.graph_store.get_neighbors(
                                self.memory_index_service.graph_store.node_key(item_type, int(item_id)),
                                depth=1,
                            ),
                        }
                    )
                except Exception as exc:
                    neighbors.append({"source_type": item_type, "source_id": item_id, "error": str(exc)})
        return neighbors

    def persisted_from_gate(
        self,
        gate_results: List[Dict[str, Any]],
        target_type: str,
        project_id: Optional[int],
        review_id: int,
    ) -> List[Dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in gate_results:
            if item.get("target_type") != target_type or not item.get("persisted_id"):
                continue
            candidate = dict(item.get("candidate") or {})
            candidate.update(
                {
                    "id": item["persisted_id"],
                    "project_id": project_id,
                    "review_id": review_id,
                    "operation": item.get("operation") or candidate.get("operation") or "",
                    "status": candidate.get("status") or ("open" if target_type == "problem" else "active"),
                }
            )
            rows.append(candidate)
        return rows

    def upsert_global_target_node(
        self,
        *,
        target_type: str,
        target_id: int,
        title: str,
        content: str,
        metadata: Dict[str, Any],
        daily_graph_key: Optional[str],
        relation_type: str,
        node_type: str,
    ) -> int:
        node_key = f"{target_type}:{target_id}"
        node_id = self.global_graph_repository.upsert_node(
            node_key=node_key,
            node_type=node_type,
            ref_type=target_type,
            ref_id=target_id,
            title=title,
            content=content,
            confidence=float(metadata.get("confidence") or 0.0),
            metadata=metadata,
        )
        if daily_graph_key:
            self.global_graph_repository.upsert_edge(
                source_node_key=node_key,
                target_node_key=daily_graph_key,
                relation_type=relation_type,
                weight=1.0,
                metadata=metadata,
            )
        return node_id

    @staticmethod
    def candidate_skip_gate_results(candidate_results: List[Dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in candidate_results
            if item.get("target_type") in {"memory", "problem", "skill"}
            and item.get("validation_status") in {"failed", "skipped"}
        ]

    @staticmethod
    def enrich_gate_record(
        gate_record: dict[str, Any],
        candidate: Dict[str, Any],
        candidate_index: int,
    ) -> None:
        gate_record["candidate_index"] = candidate_index
        gate_record["merge_key"] = str(candidate.get("merge_key") or "")
        gate_record["validation_status"] = "valid"
        gate_record["skip_reason"] = gate_record.get("reason") if gate_record.get("operation") == "skip" else ""
        gate_record["evidence_refs"] = candidate.get("evidence_refs") or []

    @staticmethod
    def append_candidate_nodes(nodes: list[dict[str, Any]], node_type: str, values: list[Any]) -> None:
        existing_keys = {str(node.get("node_key") or "") for node in nodes}
        for index, value in enumerate(values, start=1):
            node_key = f"{node_type}:{index}"
            if node_key in existing_keys:
                continue
            content = value.model_dump() if hasattr(value, "model_dump") else value
            nodes.append(
                {
                    "node_key": node_key,
                    "node_type": node_type,
                    "ref_type": "",
                    "ref_id": None,
                    "title": node_type,
                    "content": str(content),
                    "confidence": float(content.get("confidence") or 0.0) if isinstance(content, dict) else 0.0,
                    "metadata": {"candidate_index": index},
                }
            )
            existing_keys.add(node_key)

    @staticmethod
    def normalize_daily_node(node: Dict[str, Any]) -> Dict[str, Any]:
        node_key = str(node.get("node_key") or node.get("node_id") or "").strip()
        return {
            "node_key": node_key,
            "node_type": str(node.get("node_type") or "other"),
            "ref_type": str(node.get("ref_type") or node.get("source_type") or ""),
            "ref_id": node.get("ref_id") or node.get("source_id"),
            "title": str(node.get("title") or node.get("label") or node_key),
            "content": str(node.get("content") or node.get("description") or ""),
            "confidence": float(node.get("confidence") or 0.0),
            "metadata": dict(node.get("metadata") or {}),
        }

    @staticmethod
    def normalize_daily_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source_node_key": str(edge.get("source_node_key") or edge.get("source") or ""),
            "target_node_key": str(edge.get("target_node_key") or edge.get("target") or ""),
            "relation_type": str(edge.get("relation_type") or "RELATED_TO"),
            "weight": float(edge.get("weight") or 1.0),
            "evidence_event_ids": edge.get("evidence_event_ids") or edge.get("evidence") or [],
            "metadata": dict(edge.get("metadata") or {}),
        }

    @staticmethod
    def stable_merge_key(*parts: Any) -> str:
        text = "|".join(str(part or "") for part in parts)
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return f"{parts[0]}:{digest}"

    @staticmethod
    def empty_index_sync_status(parse_status: str, reason: str = "") -> Dict[str, Any]:
        skipped = {
            "status": "skipped",
            "reason": reason or "not yet executed",
            "errors": [],
            "results": [],
        }
        return {
            "parse_status": parse_status,
            "vector": dict(skipped),
            "graph": dict(skipped),
        }

    @staticmethod
    def aggregate_sync_status(status: Dict[str, Any]) -> str:
        attempted = int(status.get("attempted") or 0)
        upserted = int(status.get("upserted") or 0)
        errors = status.get("errors") or []
        if attempted == 0:
            return "skipped"
        if errors and upserted > 0:
            return "partial"
        if errors:
            return "failed"
        return "success"

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
