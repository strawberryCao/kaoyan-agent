import json
import random
from typing import Any, Dict, Optional

from config import Settings
from services.llm_client import safe_generate_with_llm


SIGN_LEVELS = ["上上签", "上吉", "中吉", "小吉", "平签"]


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


def int_between(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


class InterventionAgent:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings

    def generate_daily_sign(self) -> Dict[str, Any]:
        fallback = random.choice(
            [
                {
                    "sign_level": "中吉",
                    "sign_text": "宜小步推进，忌空想计划。",
                    "today_advice": "先完成一个 15 分钟任务，再决定是否继续。",
                    "action": "从今日作战台里选一个最短任务开始。",
                },
                {
                    "sign_level": "上吉",
                    "sign_text": "先稳住节奏，再追求速度。",
                    "today_advice": "把最容易拖延的任务切成 2 个小步骤。",
                    "action": "完成一道错题复盘并标记错因。",
                },
                {
                    "sign_level": "平签",
                    "sign_text": "少比较，多回到手里的题。",
                    "today_advice": "今天只追踪实际完成量，不评价状态好坏。",
                    "action": "做 5 分钟低门槛启动任务。",
                },
            ]
        )
        prompt = """
请生成一张考研每日上岸签。只返回 JSON，不要 Markdown。
字段：sign_level、sign_text、today_advice、action。
sign_level 必须是 上上签/上吉/中吉/小吉/平签 之一。
内容要轻量、有行动感，不要玄学化。
""".strip()
        raw = safe_generate_with_llm(
            prompt=prompt,
            fallback=json.dumps(fallback, ensure_ascii=False),
            settings=self.settings,
            system_prompt="你是考研学习干预助手，负责给用户一个低压力但可执行的今日提示。",
            temperature=0.7,
        )
        parsed = parse_json_object(raw) or fallback
        return self.normalize_sign(parsed, fallback)

    def generate_random_task(self) -> Dict[str, Any]:
        fallback = random.choice(
            [
                {
                    "title": "复刷昨天的一道错题",
                    "subject": "综合",
                    "estimated_minutes": 15,
                    "reason": "用低成本方式恢复学习手感。",
                },
                {
                    "title": "整理 3 个今天最容易忘的知识点",
                    "subject": "综合",
                    "estimated_minutes": 10,
                    "reason": "先把模糊点显性化，后续才方便干预。",
                },
                {
                    "title": "做 1 道当前章节的基础题",
                    "subject": "综合",
                    "estimated_minutes": 12,
                    "reason": "用短任务确认当前章节是否能进入状态。",
                },
            ]
        )
        prompt = """
请生成一个低压力考研学习任务。只返回 JSON，不要 Markdown。
字段：title、subject、estimated_minutes、reason。
estimated_minutes 控制在 5-20 分钟。
""".strip()
        raw = safe_generate_with_llm(
            prompt=prompt,
            fallback=json.dumps(fallback, ensure_ascii=False),
            settings=self.settings,
            system_prompt="你是考研学习干预助手，任务必须小、明确、可立刻开始。",
            temperature=0.5,
        )
        parsed = parse_json_object(raw) or fallback
        return self.normalize_task(parsed, fallback, max_minutes=20)

    def generate_soothing_task(self, user_state: str) -> Dict[str, Any]:
        fallback = {
            "title": "打开错题复刷池，只看第一道错题的错因标签",
            "subject": "低能量启动",
            "estimated_minutes": 3,
            "reason": "当前不适合安排大任务，先完成一个低门槛启动动作。",
        }
        prompt = f"""
用户当前状态：{user_state}

请生成一个 3-5 分钟的考研低能量最小行动任务。只返回 JSON，不要 Markdown。
字段：title、subject、estimated_minutes、reason。
任务必须具体、轻量、不会增加压力。
""".strip()
        raw = safe_generate_with_llm(
            prompt=prompt,
            fallback=json.dumps(fallback, ensure_ascii=False),
            settings=self.settings,
            system_prompt="你是考研学习安抚和最小行动助手，不做心理诊断，只给可执行小动作。",
            temperature=0.5,
        )
        parsed = parse_json_object(raw) or fallback
        return self.normalize_task(parsed, fallback, max_minutes=5)

    def normalize_sign(
        self,
        sign: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        level = str(sign.get("sign_level") or "").strip()
        if level not in SIGN_LEVELS:
            level = fallback["sign_level"]
        return {
            "sign_level": level,
            "sign_text": str(sign.get("sign_text") or fallback["sign_text"]).strip(),
            "today_advice": str(
                sign.get("today_advice") or fallback["today_advice"]
            ).strip(),
            "action": str(sign.get("action") or fallback["action"]).strip(),
        }

    def normalize_task(
        self,
        task: Dict[str, Any],
        fallback: Dict[str, Any],
        max_minutes: int,
    ) -> Dict[str, Any]:
        return {
            "title": str(task.get("title") or fallback["title"]).strip(),
            "subject": str(task.get("subject") or fallback["subject"]).strip(),
            "estimated_minutes": int_between(
                task.get("estimated_minutes"),
                fallback["estimated_minutes"],
                1,
                max_minutes,
            ),
            "reason": str(task.get("reason") or fallback["reason"]).strip(),
        }
