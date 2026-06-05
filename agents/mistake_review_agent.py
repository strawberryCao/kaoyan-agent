import json
from typing import Any, Dict, Optional

from config import Settings
from services.llm_client import safe_generate_with_llm


ALLOWED_MISTAKE_REASONS = {
    "concept_gap",
    "method_gap",
    "calculation_error",
    "careless_error",
    "memory_gap",
    "expression_gap",
    "unknown",
}


MISTAKE_REASON_LABELS = {
    "concept_gap": "概念不清",
    "method_gap": "方法迁移不足",
    "calculation_error": "计算错误",
    "careless_error": "粗心审题",
    "memory_gap": "知识遗忘",
    "expression_gap": "表达不规范",
    "unknown": "暂时无法判断",
}


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    candidates = [text.strip()]
    if text.strip().startswith("```"):
        lines = text.strip().splitlines()
        fenced = "\n".join(lines[1:])
        if fenced.rstrip().endswith("```"):
            fenced = fenced.rstrip()
            fenced = fenced[: fenced.rfind("```")]
        candidates.append(fenced.strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def clamp_priority(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 1
    return max(1, min(5, number))


def normalize_text_list(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


class MistakeReviewAgent:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings

    def generate_card(
        self,
        subject: str,
        chapter: str,
        question: str,
        user_reason: str = "",
    ) -> Dict[str, Any]:
        fallback = self.build_fallback_card(subject, chapter, question, user_reason)
        prompt = f"""
请为考研错题生成一张结构化错题卡。只返回 JSON，不要 Markdown。

字段：
- knowledge_points: 字符串或字符串数组
- mistake_reason: 必须是 concept_gap/method_gap/calculation_error/careless_error/memory_gap/expression_gap/unknown 之一
- analysis: 2-4 句中文简要分析
- review_priority: 1-5 的整数，5 表示最优先复刷

科目：{subject}
章节：{chapter}
错题内容：{question}
用户自述错因：{user_reason}
""".strip()
        raw = safe_generate_with_llm(
            prompt=prompt,
            fallback=json.dumps(fallback, ensure_ascii=False),
            settings=self.settings,
            system_prompt="你是考研错题复刷助手，负责把错题归因为可跟踪的复刷卡片。",
            temperature=0.2,
        )
        parsed = parse_json_object(raw) or fallback
        return self.normalize_card(parsed, fallback)

    def build_fallback_card(
        self,
        subject: str,
        chapter: str,
        question: str,
        user_reason: str = "",
    ) -> Dict[str, Any]:
        reason = self.infer_reason(user_reason or question)
        chapter_text = chapter.strip() or "当前章节"
        subject_text = subject.strip() or "当前科目"
        return {
            "knowledge_points": f"{subject_text} / {chapter_text} 的核心概念与典型题型",
            "mistake_reason": reason,
            "analysis": (
                "这是 fallback 演示分析：系统已记录这道错题，并根据题面和自述错因生成复刷卡片。"
                "建议先复盘错因标签，再用同章节的相邻题型验证是否真正掌握。"
            ),
            "review_priority": 3,
        }

    def infer_reason(self, text: str) -> str:
        text = text or ""
        if any(keyword in text for keyword in ["计算", "算错", "符号", "化简"]):
            return "calculation_error"
        if any(keyword in text for keyword in ["粗心", "看错", "审题", "漏看"]):
            return "careless_error"
        if any(keyword in text for keyword in ["忘", "记不住", "背不出"]):
            return "memory_gap"
        if any(keyword in text for keyword in ["方法", "思路", "不会迁移", "套不出"]):
            return "method_gap"
        if any(keyword in text for keyword in ["概念", "定义", "不清楚", "理解"]):
            return "concept_gap"
        if any(keyword in text for keyword in ["表达", "书写", "步骤", "规范"]):
            return "expression_gap"
        return "unknown"

    def normalize_card(
        self,
        card: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        reason = str(card.get("mistake_reason") or "").strip()
        if reason not in ALLOWED_MISTAKE_REASONS:
            reason = fallback["mistake_reason"]

        return {
            "knowledge_points": normalize_text_list(
                card.get("knowledge_points") or fallback["knowledge_points"]
            ),
            "mistake_reason": reason,
            "analysis": str(card.get("analysis") or fallback["analysis"]).strip(),
            "review_priority": clamp_priority(
                card.get("review_priority", fallback["review_priority"])
            ),
        }
