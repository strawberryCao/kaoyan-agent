import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from kaoyan_agent.schemas.nightly_memory import (
    DailyGraphEdge,
    DailyGraphNode,
    DiscoveredProblem,
    EpisodicMemory,
    EvidenceLink,
    EvidenceRef,
    KeyEvent,
    MemoryOperation,
    MemoryType,
    MemoryUpdate,
    NextAction,
    ProblemOperation,
    ProblemStatus,
    ProblemType,
    SemanticMemory,
    SkillMemoryUpdate,
    SkillOperation,
)


@dataclass
class NormalizedNightlyPayload:
    payload: dict[str, Any]
    parse_status: str
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    normalization_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    candidate_results: list[dict[str, Any]] = field(default_factory=list)


ALLOWED_MEMORY_TYPES = set(get_args(MemoryType))
ALLOWED_MEMORY_OPERATIONS = set(get_args(MemoryOperation))
ALLOWED_PROBLEM_TYPES = set(get_args(ProblemType))
ALLOWED_PROBLEM_OPERATIONS = set(get_args(ProblemOperation))
ALLOWED_PROBLEM_STATUSES = set(get_args(ProblemStatus))
ALLOWED_SKILL_OPERATIONS = set(get_args(SkillOperation))

MEMORY_TYPE_ALIASES = {
    "episode": "episodic",
    "episodic_memory": "episodic",
    "semantic_memory": "semantic",
    "profile": "user_profile",
    "user": "user_profile",
    "preference_memory": "preference",
    "state": "learning_state",
    "status": "learning_status",
    "fact": "strategy",
    "long_term": "strategy",
}


def normalize_nightly_payload(
    payload: Any,
    raw_events: list[dict[str, Any]] | None = None,
) -> NormalizedNightlyPayload:
    if not isinstance(payload, dict):
        return NormalizedNightlyPayload(
            payload=empty_payload("Nightly JSON root is not an object."),
            parse_status="failed",
            validation_errors=[
                {
                    "target_type": "payload",
                    "validation_status": "failed",
                    "error": "Nightly JSON root is not an object.",
                }
            ],
        )

    raw_events = raw_events or []
    raw_event_lookup = _raw_event_lookup(raw_events)
    errors: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []

    candidate_problems = _normalize_problems(
        payload.get("candidate_problems")
        if payload.get("candidate_problems") is not None
        else payload.get("discovered_problems") or [],
        raw_event_lookup,
        errors,
        candidate_results,
    )
    memory_updates = _normalize_memories(
        payload.get("memory_updates") or [],
        raw_event_lookup,
        errors,
        candidate_results,
    )
    skill_updates = _normalize_skills(
        payload.get("skill_observations")
        if payload.get("skill_observations") is not None
        else payload.get("skill_updates") or [],
        raw_event_lookup,
        errors,
        candidate_results,
    )
    daily_graph_nodes = _normalize_daily_graph_nodes(
        payload.get("daily_graph_nodes"),
        payload.get("daily_memory_graph"),
        errors,
        diagnostics,
    )
    daily_graph_edges = _normalize_daily_graph_edges(
        payload.get("daily_graph_edges"),
        payload.get("daily_memory_graph"),
        errors,
        diagnostics,
    )

    normalized: dict[str, Any] = {
        "daily_summary": str(payload.get("daily_summary") or "").strip()
        or "本次晚间回顾已完成结构化解析。",
        "key_events": _validate_model_list(
            KeyEvent,
            payload.get("key_events") or [],
            "key_event",
            errors,
        ),
        "episodic_memories": _normalize_episodic_memories(
            payload.get("episodic_memories") or [],
            raw_event_lookup,
            errors,
        ),
        "semantic_memories": _normalize_semantic_memories(
            payload.get("semantic_memories") or [],
            raw_event_lookup,
            errors,
        ),
        "daily_graph_nodes": daily_graph_nodes,
        "daily_graph_edges": daily_graph_edges,
        "daily_memory_graph": {
            "nodes": _legacy_graph_nodes(daily_graph_nodes),
            "edges": _legacy_graph_edges(daily_graph_edges),
            "summary": _daily_graph_summary(payload),
        },
        "discovered_problems": candidate_problems,
        "candidate_problems": candidate_problems,
        "evidence_links": _validate_model_list(
            EvidenceLink,
            payload.get("evidence_links") or [],
            "evidence_link",
            errors,
        ),
        "memory_updates": memory_updates,
        "skill_observations": skill_updates,
        "skill_updates": skill_updates,
        "next_actions": _validate_model_list(
            NextAction,
            payload.get("next_actions") or [],
            "next_action",
            errors,
        ),
    }

    parse_status = "partial_success" if _has_candidate_failure(candidate_results, errors) else "success"
    return NormalizedNightlyPayload(
        payload=normalized,
        parse_status=parse_status,
        validation_errors=errors,
        normalization_diagnostics=diagnostics,
        candidate_results=candidate_results,
    )


def empty_payload(reason: str) -> dict[str, Any]:
    return {
        "daily_summary": f"本次晚间记忆更新未能完成结构化解析：{reason}",
        "key_events": [],
        "episodic_memories": [],
        "semantic_memories": [],
        "daily_graph_nodes": [],
        "daily_graph_edges": [],
        "daily_memory_graph": {"nodes": [], "edges": [], "summary": ""},
        "discovered_problems": [],
        "candidate_problems": [],
        "evidence_links": [],
        "memory_updates": [],
        "skill_observations": [],
        "skill_updates": [],
        "next_actions": [
            {
                "action_type": "follow_up",
                "content": "检查模型 JSON 输出格式后重新运行晚间回顾。",
                "related_problem": "",
                "priority": 3,
            }
        ],
    }


def _normalize_episodic_memories(
    values: Any,
    raw_event_lookup: dict[int, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(_as_list(values)):
        candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
        if "occurred_at" in candidate and not candidate.get("event_date"):
            candidate["event_date"] = str(candidate.get("occurred_at") or "")
        if "source_event_ids" in candidate and not candidate.get("evidence_event_ids"):
            candidate["evidence_event_ids"] = _int_list(candidate.get("source_event_ids"))
        if not candidate.get("title"):
            candidate["title"] = str(candidate.get("event_type") or "Episodic memory")
        candidate["evidence_refs"] = _refs_from_ids(
            candidate.get("evidence_refs"),
            candidate.get("evidence_event_ids"),
            raw_event_lookup,
        )
        try:
            valid.append(EpisodicMemory.model_validate(candidate).model_dump())
        except ValidationError as exc:
            _append_validation_error(errors, "episodic_memory", index, exc.errors(), candidate)
    return valid


def _normalize_semantic_memories(
    values: Any,
    raw_event_lookup: dict[int, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(_as_list(values)):
        candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
        if not candidate.get("title"):
            candidate["title"] = str(candidate.get("category") or "Semantic memory")
        candidate["evidence_refs"] = _refs_from_ids(
            candidate.get("evidence_refs"),
            candidate.get("evidence_event_ids"),
            raw_event_lookup,
        )
        try:
            valid.append(SemanticMemory.model_validate(candidate).model_dump())
        except ValidationError as exc:
            _append_validation_error(errors, "semantic_memory", index, exc.errors(), candidate)
    return valid


def _normalize_daily_graph_nodes(
    explicit_nodes: Any,
    legacy_graph: Any,
    errors: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    values = _as_list(explicit_nodes)
    if not values and isinstance(legacy_graph, dict):
        values = _as_list(legacy_graph.get("nodes"))

    valid: list[dict[str, Any]] = []
    for index, raw_node in enumerate(values):
        if not isinstance(raw_node, dict):
            _append_validation_error(errors, "daily_graph_node", index, "node is not an object", raw_node)
            continue
        node = dict(raw_node)
        if "label" in node and "title" not in node:
            node["title"] = str(node.pop("label"))
            diagnostics.append(_normalization_record("daily_graph_node", index, "label", "title"))
        if node.get("title") and not node.get("content"):
            node["content"] = str(node.get("title") or "")
        if "node_id" in node and "node_key" not in node:
            node["node_key"] = str(node.pop("node_id"))
            diagnostics.append(_normalization_record("daily_graph_node", index, "node_id", "node_key"))
        if "type" in node and "node_type" not in node:
            node["node_type"] = str(node.pop("type"))
            diagnostics.append(_normalization_record("daily_graph_node", index, "type", "node_type"))
        node["node_type"] = _normalize_node_type(str(node.get("node_type") or "other"))
        try:
            valid.append(DailyGraphNode.model_validate(node).model_dump())
        except ValidationError as exc:
            _append_validation_error(errors, "daily_graph_node", index, exc.errors(), node)
    return valid


def _normalize_daily_graph_edges(
    explicit_edges: Any,
    legacy_graph: Any,
    errors: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    values = _as_list(explicit_edges)
    if not values and isinstance(legacy_graph, dict):
        values = _as_list(legacy_graph.get("edges"))

    valid: list[dict[str, Any]] = []
    for index, raw_edge in enumerate(values):
        if not isinstance(raw_edge, dict):
            _append_validation_error(errors, "daily_graph_edge", index, "edge is not an object", raw_edge)
            continue
        edge = dict(raw_edge)
        if "source" in edge and "source_node_key" not in edge:
            edge["source_node_key"] = str(edge.pop("source"))
            diagnostics.append(_normalization_record("daily_graph_edge", index, "source", "source_node_key"))
        if "target" in edge and "target_node_key" not in edge:
            edge["target_node_key"] = str(edge.pop("target"))
            diagnostics.append(_normalization_record("daily_graph_edge", index, "target", "target_node_key"))
        if "type" in edge and "relation_type" not in edge:
            edge["relation_type"] = str(edge.pop("type"))
            diagnostics.append(_normalization_record("daily_graph_edge", index, "type", "relation_type"))
        try:
            valid.append(DailyGraphEdge.model_validate(edge).model_dump())
        except ValidationError as exc:
            _append_validation_error(errors, "daily_graph_edge", index, exc.errors(), edge)
    return valid


def _normalize_node_type(value: str) -> str:
    aliases = {
        "episode": "episodic_memory",
        "episodic": "episodic_memory",
        "semantic": "semantic_memory",
        "semantic_candidate": "semantic_memory",
        "memory_candidate": "semantic_memory",
        "problem_candidate": "problem",
        "skill_candidate": "skill",
        "memory": "semantic_memory",
        "daily_graph": "daily_memory_graph",
    }
    normalized = aliases.get(value.strip(), value.strip())
    allowed = {
        "raw_event",
        "episodic_memory",
        "semantic_memory",
        "problem",
        "skill",
        "action",
        "daily_memory_graph",
        "other",
    }
    return normalized if normalized in allowed else "other"


def _legacy_graph_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    legacy_type_aliases = {
        "episodic_memory": "episode",
        "semantic_memory": "semantic_candidate",
        "daily_memory_graph": "daily_graph",
        "action": "other",
    }
    return [
        {
            "node_id": node["node_key"],
            "node_type": legacy_type_aliases.get(
                str(node.get("node_type") or ""),
                node.get("node_type") or "other",
            ),
            "title": node.get("title") or "",
            "content": node.get("content") or "",
            "ref_type": node.get("ref_type") or "",
            "ref_id": node.get("ref_id"),
            "metadata": node.get("metadata") or {},
        }
        for node in nodes
    ]


def _legacy_graph_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": edge["source_node_key"],
            "target": edge["target_node_key"],
            "relation_type": edge.get("relation_type") or "RELATED_TO",
            "weight": edge.get("weight", 1.0),
            "metadata": {
                **dict(edge.get("metadata") or {}),
                "evidence_event_ids": edge.get("evidence_event_ids") or [],
            },
        }
        for edge in edges
    ]


def _daily_graph_summary(payload: dict[str, Any]) -> str:
    graph = payload.get("daily_memory_graph")
    if isinstance(graph, dict) and graph.get("summary"):
        return str(graph.get("summary") or "")
    return str(payload.get("daily_graph_summary") or payload.get("daily_summary") or "")


def _normalize_problems(
    values: Any,
    raw_event_lookup: dict[int, dict[str, Any]],
    errors: list[dict[str, Any]],
    candidate_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(_as_list(values)):
        candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
        if not candidate:
            _skip_candidate(candidate_results, "problem", index, candidate, "invalid_candidate", errors)
            continue

        operation = _normalize_choice(candidate.get("operation"), ALLOWED_PROBLEM_OPERATIONS, "insert")
        candidate["operation"] = operation
        if operation == "skip":
            _skip_candidate(candidate_results, "problem", index, candidate, "operation_skip", errors)
            continue

        description = str(candidate.get("description") or "").strip()
        if not description:
            _skip_candidate(candidate_results, "problem", index, candidate, "description_missing", errors)
            continue

        candidate["problem_type"] = _normalize_choice(candidate.get("problem_type"), ALLOWED_PROBLEM_TYPES, "other")
        candidate["subject"] = str(candidate.get("subject") or "general").strip() or "general"
        candidate["status"] = _normalize_choice(candidate.get("status"), ALLOWED_PROBLEM_STATUSES, "open")
        candidate["description"] = description
        candidate["severity"] = _clamp_int(candidate.get("severity"), 3, 1, 5)
        candidate["confidence"] = _clamp_float(candidate.get("confidence"), 0.5, 0.0, 1.0)
        candidate["value_score"] = _clamp_int(candidate.get("value_score"), 3, 1, 5)
        candidate["evidence_refs"] = _normalize_evidence_refs(candidate, raw_event_lookup)
        candidate["evidence"] = _derive_evidence(candidate.get("evidence"), candidate["evidence_refs"], raw_event_lookup)
        if not candidate["evidence"]:
            _skip_candidate(candidate_results, "problem", index, candidate, "evidence_missing", errors)
            continue
        candidate["merge_key"] = str(candidate.get("merge_key") or "").strip() or _stable_key(
            "problem",
            candidate["problem_type"],
            candidate["subject"],
            description,
        )
        try:
            model = DiscoveredProblem.model_validate(candidate)
        except ValidationError as exc:
            _fail_candidate(candidate_results, "problem", index, candidate, exc.errors(), errors)
            continue
        dumped = model.model_dump()
        valid.append(dumped)
        candidate_results.append(_candidate_record("problem", index, dumped, "valid"))
    return valid


def _normalize_memories(
    values: Any,
    raw_event_lookup: dict[int, dict[str, Any]],
    errors: list[dict[str, Any]],
    candidate_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(_as_list(values)):
        candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
        if not candidate:
            _skip_candidate(candidate_results, "memory", index, candidate, "invalid_candidate", errors)
            continue

        operation = _normalize_choice(candidate.get("operation"), ALLOWED_MEMORY_OPERATIONS, "insert")
        candidate["operation"] = operation
        if operation == "skip":
            _skip_candidate(candidate_results, "memory", index, candidate, "operation_skip", errors)
            continue

        content = str(candidate.get("content") or "").strip()
        if not content:
            _skip_candidate(candidate_results, "memory", index, candidate, "content_missing", errors)
            continue

        memory_type = str(candidate.get("memory_type") or "strategy").strip()
        memory_type = MEMORY_TYPE_ALIASES.get(memory_type, memory_type)
        if memory_type not in ALLOWED_MEMORY_TYPES:
            _skip_candidate(candidate_results, "memory", index, candidate, "memory_type_invalid", errors)
            continue

        candidate["memory_type"] = memory_type
        candidate["content"] = content
        candidate["importance"] = _clamp_int(candidate.get("importance"), 3, 1, 5)
        candidate["confidence"] = _clamp_float(candidate.get("confidence"), 0.5, 0.0, 1.0)
        candidate["evidence_refs"] = _normalize_evidence_refs(candidate, raw_event_lookup)
        if not candidate["evidence_refs"]:
            _skip_candidate(candidate_results, "memory", index, candidate, "evidence_missing", errors)
            continue
        candidate["merge_key"] = str(candidate.get("merge_key") or "").strip() or _stable_key(
            "memory",
            memory_type,
            candidate.get("subject") or "",
            content,
        )
        try:
            model = MemoryUpdate.model_validate(candidate)
        except ValidationError as exc:
            _fail_candidate(candidate_results, "memory", index, candidate, exc.errors(), errors)
            continue
        dumped = model.model_dump()
        valid.append(dumped)
        candidate_results.append(_candidate_record("memory", index, dumped, "valid"))
    return valid


def _normalize_skills(
    values: Any,
    raw_event_lookup: dict[int, dict[str, Any]],
    errors: list[dict[str, Any]],
    candidate_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(_as_list(values)):
        candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
        if not candidate:
            _skip_candidate(candidate_results, "skill", index, candidate, "invalid_candidate", errors)
            continue

        operation = _normalize_choice(candidate.get("operation"), ALLOWED_SKILL_OPERATIONS, "insert")
        candidate["operation"] = operation
        if operation == "skip":
            _skip_candidate(candidate_results, "skill", index, candidate, "operation_skip", errors)
            continue

        procedure = candidate.get("procedure") if isinstance(candidate.get("procedure"), dict) else {}
        if not procedure:
            _skip_candidate(candidate_results, "skill", index, candidate, "not_reusable_skill", errors)
            continue

        evidence_refs = _normalize_evidence_refs(candidate, raw_event_lookup)
        evidence = _derive_evidence(candidate.get("evidence"), evidence_refs, raw_event_lookup)
        if not evidence and not evidence_refs:
            _skip_candidate(candidate_results, "skill", index, candidate, "evidence_missing", errors)
            continue

        skill_name = str(candidate.get("skill_name") or "").strip() or _make_skill_name(candidate)
        if not skill_name:
            _skip_candidate(candidate_results, "skill", index, candidate, "skill_name_missing", errors)
            continue

        candidate["skill_name"] = skill_name
        candidate["procedure"] = procedure
        candidate["trigger"] = candidate.get("trigger") if isinstance(candidate.get("trigger"), dict) else {}
        candidate["confidence"] = _clamp_float(candidate.get("confidence"), 0.5, 0.0, 1.0)
        candidate["effectiveness_score"] = _clamp_float(candidate.get("effectiveness_score"), 0.0, 0.0, 1.0)
        candidate["evidence"] = evidence
        candidate["evidence_refs"] = evidence_refs
        candidate["merge_key"] = str(candidate.get("merge_key") or "").strip() or _stable_key(
            "skill",
            skill_name,
            json.dumps(procedure, ensure_ascii=False, sort_keys=True),
        )
        try:
            model = SkillMemoryUpdate.model_validate(candidate)
        except ValidationError as exc:
            _fail_candidate(candidate_results, "skill", index, candidate, exc.errors(), errors)
            continue
        dumped = model.model_dump()
        valid.append(dumped)
        candidate_results.append(_candidate_record("skill", index, dumped, "valid"))
    return valid


def _validate_model_list(
    model_type: type[BaseModel],
    values: Any,
    target_type: str,
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for index, value in enumerate(_as_list(values)):
        try:
            valid.append(model_type.model_validate(value).model_dump())
        except ValidationError as exc:
            _append_validation_error(errors, target_type, index, exc.errors(), value)
    return valid


def _normalize_evidence_refs(
    candidate: dict[str, Any],
    raw_event_lookup: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    return _refs_from_ids(candidate.get("evidence_refs"), candidate.get("source_event_ids"), raw_event_lookup)


def _refs_from_ids(
    raw_refs: Any,
    raw_ids: Any,
    raw_event_lookup: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, str]] = set()

    for item in _as_list(raw_refs):
        if isinstance(item, int):
            ref = {"source_type": "raw_event", "source_id": item, "quote": "", "note": ""}
        elif isinstance(item, dict):
            ref = dict(item)
        else:
            continue
        ref.setdefault("source_type", "raw_event")
        ref.setdefault("source_id", None)
        ref.setdefault("quote", "")
        ref.setdefault("note", "")
        source_id = _optional_int(ref.get("source_id"))
        if source_id is not None:
            ref["source_id"] = source_id
        validated = _validate_evidence_ref(ref)
        if not validated:
            continue
        key = (validated["source_type"], validated["source_id"], validated["quote"])
        if key not in seen:
            refs.append(validated)
            seen.add(key)

    for source_id in _int_list(raw_ids):
        event = raw_event_lookup.get(source_id, {})
        ref = {
            "source_type": "raw_event",
            "source_id": source_id,
            "quote": str(event.get("content") or "")[:240],
            "note": "derived_from_event_ids",
        }
        validated = _validate_evidence_ref(ref)
        if not validated:
            continue
        key = (validated["source_type"], validated["source_id"], validated["quote"])
        if key not in seen:
            refs.append(validated)
            seen.add(key)
    return refs


def _validate_evidence_ref(ref: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return EvidenceRef.model_validate(ref).model_dump()
    except ValidationError:
        return None


def _derive_evidence(
    value: Any,
    evidence_refs: list[dict[str, Any]],
    raw_event_lookup: dict[int, dict[str, Any]],
) -> list[str]:
    evidence = [str(item).strip() for item in _as_list(value) if str(item).strip()]
    for ref in evidence_refs:
        quote = str(ref.get("quote") or "").strip()
        if quote:
            evidence.append(quote)
            continue
        source_id = ref.get("source_id")
        if isinstance(source_id, int) and source_id in raw_event_lookup:
            content = str(raw_event_lookup[source_id].get("content") or "").strip()
            if content:
                evidence.append(content[:240])
    return _dedupe_strings(evidence)


def _candidate_record(
    target_type: str,
    index: int,
    candidate: dict[str, Any],
    validation_status: str,
    skip_reason: str = "",
    error: Any = "",
) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "candidate_index": index,
        "operation": "skip" if validation_status != "valid" else str(candidate.get("operation") or "insert"),
        "target_id": candidate.get("target_memory_id")
        or candidate.get("target_problem_id")
        or candidate.get("target_skill_id"),
        "merge_key": str(candidate.get("merge_key") or ""),
        "similarity": 0.0,
        "lexical_score": 0.0,
        "embedding_status": "not_called",
        "embedding_provider": "",
        "embedding_model": "",
        "reason": skip_reason,
        "error": _error_text(error),
        "validation_status": validation_status,
        "skip_reason": skip_reason,
        "evidence_refs": candidate.get("evidence_refs") or [],
        "candidate": candidate,
    }


def _skip_candidate(
    candidate_results: list[dict[str, Any]],
    target_type: str,
    index: int,
    candidate: dict[str, Any],
    reason: str,
    errors: list[dict[str, Any]],
) -> None:
    record = _candidate_record(target_type, index, candidate, "skipped", reason, reason)
    candidate_results.append(record)
    errors.append(
        {
            "target_type": target_type,
            "candidate_index": index,
            "validation_status": "skipped",
            "skip_reason": reason,
            "candidate": candidate,
        }
    )


def _fail_candidate(
    candidate_results: list[dict[str, Any]],
    target_type: str,
    index: int,
    candidate: dict[str, Any],
    error: Any,
    errors: list[dict[str, Any]],
) -> None:
    record = _candidate_record(target_type, index, candidate, "failed", "pydantic_validation_failed", error)
    candidate_results.append(record)
    _append_validation_error(errors, target_type, index, error, candidate)


def _append_validation_error(
    errors: list[dict[str, Any]],
    target_type: str,
    index: int,
    error: Any,
    candidate: Any,
) -> None:
    errors.append(
        {
            "target_type": target_type,
            "candidate_index": index,
            "validation_status": "failed",
            "error": _error_text(error),
            "candidate": candidate,
        }
    )


def _normalization_record(target_type: str, index: int, source_field: str, target_field: str) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "candidate_index": index,
        "source_field": source_field,
        "target_field": target_field,
        "action": "mapped",
    }


def _has_candidate_failure(
    candidate_results: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> bool:
    if any(item.get("validation_status") in {"failed", "skipped"} for item in candidate_results):
        return True
    return any(item.get("validation_status") == "failed" for item in errors)


def _raw_event_lookup(raw_events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for event in raw_events:
        source_id = _optional_int(event.get("id"))
        if source_id is not None:
            lookup[source_id] = event
    return lookup


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_list(value: Any) -> list[int]:
    ids: list[int] = []
    for item in _as_list(value):
        number = _optional_int(item)
        if number is not None:
            ids.append(number)
    return ids


def _normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_key(prefix: str, *parts: Any) -> str:
    text = " | ".join(_normalize_text(part) for part in parts if _normalize_text(part))
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else "empty"
    return f"{prefix}:{digest}"


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _make_skill_name(candidate: dict[str, Any]) -> str:
    description = str(candidate.get("description") or "").strip()
    if description:
        return description[:30]
    procedure = candidate.get("procedure")
    if isinstance(procedure, dict):
        for value in procedure.values():
            if isinstance(value, str) and value.strip():
                return value.strip()[:30]
            if isinstance(value, list) and value:
                first = str(value[0]).strip()
                if first:
                    return first[:30]
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _error_text(error: Any) -> str:
    if isinstance(error, str):
        return error
    try:
        return json.dumps(error, ensure_ascii=False)
    except TypeError:
        return str(error)
