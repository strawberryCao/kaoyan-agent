import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.memory.normalization import (
    NormalizedNightlyPayload,
    empty_payload,
    normalize_nightly_payload,
)
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.services.llm_client import (
    LLMConfigError,
    run_structured_agent,
    run_text_agent,
)


@dataclass
class NightlyMemoryResult:
    output: NightlyMemoryUpdateOutput
    raw_response: str
    parse_status: str
    error_message: str = ""
    validation_errors: List[Dict[str, Any]] = field(default_factory=list)
    normalization_diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    candidate_results: List[Dict[str, Any]] = field(default_factory=list)


class NightlyMemoryParseError(ValueError):
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


class NightlyMemoryAgent:
    """Generate and locally validate nightly memory candidates."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompt_registry: Optional[PromptRegistry] = None,
        prefer_structured_output: bool = False,
    ):
        self.settings = settings
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.prefer_structured_output = prefer_structured_output

    def run(
        self,
        review_date: str,
        sessions: Optional[List[Dict[str, Any]]] = None,
        conversations: Optional[List[Dict[str, Any]]] = None,
        raw_events: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        open_problems: Optional[List[Dict[str, Any]]] = None,
        skill_memories: Optional[List[Dict[str, Any]]] = None,
        recent_daily_graphs: Optional[List[Dict[str, Any]]] = None,
        global_graph_nodes: Optional[List[Dict[str, Any]]] = None,
        global_graph_edges: Optional[List[Dict[str, Any]]] = None,
        focus_sessions: Optional[List[Dict[str, Any]]] = None,
        mistake_cards: Optional[List[Dict[str, Any]]] = None,
        study_tasks: Optional[List[Dict[str, Any]]] = None,
    ) -> NightlyMemoryResult:
        sessions = sessions or []
        conversations = conversations or []
        raw_events = raw_events or []
        memories = memories or []
        open_problems = open_problems or []
        skill_memories = skill_memories or []
        recent_daily_graphs = recent_daily_graphs or []
        global_graph_nodes = global_graph_nodes or []
        global_graph_edges = global_graph_edges or []
        focus_sessions = focus_sessions or []
        mistake_cards = mistake_cards or []
        study_tasks = study_tasks or []

        payload = {
            "review_date": review_date,
            "sessions": sessions,
            "conversations": conversations,
            "raw_events": raw_events,
            "existing_memories": memories,
            "open_problems": open_problems,
            "skill_memories": skill_memories,
            "recent_daily_graphs": recent_daily_graphs,
            "global_graph_nodes": global_graph_nodes,
            "global_graph_edges": global_graph_edges,
            "focus_sessions": focus_sessions,
            "mistake_cards": mistake_cards,
            "study_tasks": study_tasks,
        }
        try:
            prompt = self.prompt_registry.get("nightly_memory_update")
        except (FileNotFoundError, KeyError) as exc:
            return self.failed_result(f"Prompt file is missing: {exc}", raw_response="")

        user_message = (
            "Generate the nightly memory update JSON for this data:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

        structured_error = ""
        if self.prefer_structured_output:
            try:
                output, raw_response = self.run_langchain_structured(prompt, user_message)
                return NightlyMemoryResult(
                    output=output,
                    raw_response=raw_response,
                    parse_status="success",
                )
            except LLMConfigError as exc:
                return self.failed_result(f"LangChain is not configured: {exc}", raw_response="")
            except Exception as exc:
                structured_error = f"LangChain structured output failed: {exc}"

        try:
            return self.run_raw_json_fallback(
                prompt,
                user_message,
                raw_events=raw_events,
                structured_error=structured_error,
            )
        except LLMConfigError as exc:
            prefix = f"{structured_error}; " if structured_error else ""
            return self.failed_result(
                f"{prefix}JSON text completion is not configured: {exc}",
                raw_response="",
            )
        except NightlyMemoryParseError as exc:
            prefix = f"{structured_error}; " if structured_error else ""
            return self.failed_result(
                f"{prefix}JSON fallback validation failed: {exc}",
                raw_response=exc.raw_response,
            )
        except Exception as exc:
            prefix = f"{structured_error}; " if structured_error else ""
            return self.failed_result(f"{prefix}JSON fallback failed: {exc}", raw_response="")

    def run_langchain_structured(
        self,
        system_prompt: str,
        user_message: str,
    ) -> tuple[NightlyMemoryUpdateOutput, str]:
        output = run_structured_agent(
            NightlyMemoryUpdateOutput,
            user_message,
            system_prompt=system_prompt,
            settings=self.settings,
            temperature=0.2,
        )
        return output, json.dumps(output.model_dump(), ensure_ascii=False)

    def run_raw_json_fallback(
        self,
        system_prompt: str,
        user_message: str,
        raw_events: Optional[List[Dict[str, Any]]] = None,
        structured_error: str = "",
    ) -> NightlyMemoryResult:
        fallback_system_prompt = (
            f"{system_prompt}\n\n"
            "The provider may not support native structured output. "
            "Return one JSON object only. The application will normalize and "
            "Pydantic-validate each candidate locally before any long-term writes. "
            "Do not wrap JSON in Markdown and do not include explanatory text."
        )
        raw_response = run_text_agent(
            [{"role": "user", "content": user_message}],
            system_prompt=fallback_system_prompt,
            settings=self.settings,
            temperature=0.2,
        )
        normalized = self.validate_response(raw_response, raw_events=raw_events or [])
        output = NightlyMemoryUpdateOutput.model_validate(normalized.payload)
        return NightlyMemoryResult(
            output=output,
            raw_response=raw_response,
            parse_status=normalized.parse_status,
            error_message="",
            validation_errors=normalized.validation_errors,
            normalization_diagnostics=normalized.normalization_diagnostics,
            candidate_results=normalized.candidate_results,
        )

    def validate_response(
        self,
        raw_response: str,
        raw_events: Optional[List[Dict[str, Any]]] = None,
    ) -> NormalizedNightlyPayload:
        try:
            json_text = self.extract_json_object(raw_response)
            payload = json.loads(json_text)
            normalized = normalize_nightly_payload(payload, raw_events=raw_events or [])
            if normalized.parse_status == "failed":
                message = (
                    normalized.validation_errors[0].get("error")
                    if normalized.validation_errors
                    else "no usable nightly memory payload"
                )
                raise ValueError(str(message))
            return normalized
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise NightlyMemoryParseError(str(exc), raw_response=raw_response) from exc

    @staticmethod
    def extract_json_object(raw_response: str) -> str:
        text = (raw_response or "").strip()
        if not text:
            raise ValueError("empty fallback response")

        fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced_match:
            text = fenced_match.group(1).strip()

        if text.startswith("{") and text.endswith("}"):
            return text

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("fallback response does not contain a JSON object")
        return text[start : end + 1]

    @staticmethod
    def normalize_daily_graph_contract(payload: Any) -> None:
        """Backward-compatible limited graph alias normalization."""

        if not isinstance(payload, dict):
            return
        normalized = normalize_nightly_payload(payload)
        payload["daily_memory_graph"] = normalized.payload.get("daily_memory_graph", {})

    def failed_result(self, reason: str, raw_response: str) -> NightlyMemoryResult:
        fallback_payload = empty_payload(reason)
        output = NightlyMemoryUpdateOutput.model_validate(fallback_payload)
        validation_errors = [
            {
                "target_type": "payload",
                "validation_status": "failed",
                "error": reason,
            }
        ]
        return NightlyMemoryResult(
            output=output,
            raw_response=raw_response,
            parse_status="failed",
            error_message=reason,
            validation_errors=validation_errors,
            normalization_diagnostics=[],
            candidate_results=[],
        )
