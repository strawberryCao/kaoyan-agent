import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ROOT_DIR, Settings
from services.llm_client import LLMClient, LLMConfigError


PROMPT_PATH = ROOT_DIR / "prompts" / "nightly_memory_update_prompt.txt"


@dataclass
class NightlyMemoryResult:
    result: Dict[str, Any]
    raw_response: str
    parse_status: str


class NightlyMemoryAgent:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompt_path: Path = PROMPT_PATH,
    ):
        self.settings = settings
        self.prompt_path = prompt_path

    def run(
        self,
        review_date: str,
        sessions: List[Dict[str, Any]],
        conversations: List[Dict[str, Any]],
        memories: List[Dict[str, Any]],
        open_problems: List[Dict[str, Any]],
    ) -> NightlyMemoryResult:
        payload = {
            "review_date": review_date,
            "sessions": sessions,
            "conversations": conversations,
            "existing_memories": memories,
            "open_problems": open_problems,
        }
        try:
            prompt = self.prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            fallback = self.build_fallback_result(
                f"Prompt file is missing: {self.prompt_path}",
                conversations,
            )
            return NightlyMemoryResult(
                result=fallback,
                raw_response=json.dumps(fallback, ensure_ascii=False),
                parse_status="prompt_missing",
            )

        user_message = (
            "Generate the nightly memory update JSON for this data:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

        try:
            raw_response = LLMClient(self.settings).chat(
                [{"role": "user", "content": user_message}],
                system_prompt=prompt,
                temperature=0.2,
            )
        except LLMConfigError as exc:
            fallback = self.build_fallback_result(
                f"LLM is not configured: {exc}",
                conversations,
            )
            return NightlyMemoryResult(
                result=fallback,
                raw_response=json.dumps(fallback, ensure_ascii=False),
                parse_status="llm_config_error",
            )
        except Exception as exc:
            fallback = self.build_fallback_result(
                f"LLM request failed: {exc}",
                conversations,
            )
            return NightlyMemoryResult(
                result=fallback,
                raw_response=json.dumps(fallback, ensure_ascii=False),
                parse_status="llm_request_error",
            )

        result, parse_status = self.parse_json_response(raw_response, conversations)
        return NightlyMemoryResult(
            result=result,
            raw_response=raw_response,
            parse_status=parse_status,
        )

    def parse_json_response(
        self,
        raw_response: str,
        conversations: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], str]:
        for candidate in self.response_candidates(raw_response):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return self.normalize_result(parsed), "ok"

        return (
            self.build_fallback_result("JSON parsing failed.", conversations),
            "json_parse_error",
        )

    def response_candidates(self, raw_response: str) -> List[str]:
        text = raw_response.strip()
        candidates = [text]

        if text.startswith("```"):
            lines = text.splitlines()
            fenced = "\n".join(lines[1:])
            if fenced.rstrip().endswith("```"):
                fenced = fenced.rstrip()
                fenced = fenced[: fenced.rfind("```")]
            candidates.append(fenced.strip())

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])

        return candidates

    def normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self.empty_result()
        normalized["daily_summary"] = str(result.get("daily_summary") or "")
        normalized["key_events"] = self.list_value(result.get("key_events"))
        normalized["discovered_problems"] = self.list_value(
            result.get("discovered_problems")
        )[:3]
        normalized["memory_updates"] = self.list_value(result.get("memory_updates"))
        normalized["next_actions"] = self.list_value(result.get("next_actions"))
        return normalized

    def build_fallback_result(
        self,
        reason: str,
        conversations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result = self.empty_result()
        message_count = len(conversations)
        if message_count:
            result["daily_summary"] = (
                f"今晚记忆更新未能完成结构化分析：{reason} "
                f"今天共有 {message_count} 条对话记录，已保存本次复盘记录供后续检查。"
            )
        else:
            result["daily_summary"] = (
                f"今晚记忆更新未能完成结构化分析：{reason} 今天没有可复盘的对话记录。"
            )
        result["next_actions"] = [
            {
                "action_type": "follow_up",
                "content": "检查 LLM 配置或模型 JSON 输出格式后，重新生成今晚记忆更新。",
                "related_problem": "",
                "priority": 3,
            }
        ]
        return result

    def empty_result(self) -> Dict[str, Any]:
        return {
            "daily_summary": "",
            "key_events": [],
            "discovered_problems": [],
            "memory_updates": [],
            "next_actions": [],
        }

    def list_value(self, value: Any) -> List[Any]:
        return value if isinstance(value, list) else []
