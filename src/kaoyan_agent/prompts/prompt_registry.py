from pathlib import Path
from typing import Dict, Optional

from kaoyan_agent.core.paths import NIGHTLY_MEMORY_PROMPT_PATH, PROMPTS_DIR


DEFAULT_PROMPTS: Dict[str, str] = {
    "chat.default": (
        "You are ChatAgent for Kaoyan Problem Discovery Agent. "
        "Answer the user directly and practically in the user's language. "
        "Chat is the front-stage interface; use retrieved memory and problem "
        "context when provided, but do not invent private facts."
    ),
    "query_rewriter.default": (
        "Rewrite the user's latest message for retrieval and routing. "
        "Return only the rewritten query."
    ),
    "practice_review.card": """
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
""".strip(),
    "practice_review.system": "你是考研错题复刷助手，负责把错题归因为可跟踪的复刷卡片。",
    "motivation.daily_sign": """
请生成一张考研每日上岸签。只返回 JSON，不要 Markdown。
字段：sign_level、sign_text、today_advice、action。
sign_level 必须是 top/good/steady/small/calm 之一。
内容要轻量、有行动感，不要玄学化。
""".strip(),
    "motivation.random_task": """
请生成一个低压力考研学习任务。只返回 JSON，不要 Markdown。
字段：title、subject、estimated_minutes、reason。
estimated_minutes 控制在 5-20 分钟。
""".strip(),
    "motivation.soothing_task": """
用户当前状态：{user_state}

请生成一个 3-5 分钟的考研低能量最小行动任务。只返回 JSON，不要 Markdown。
字段：title、subject、estimated_minutes、reason。
任务必须具体、轻量、不会增加压力。
""".strip(),
    "motivation.system": "你是考研学习干预助手，任务必须小、明确、可立刻开始。",
    "motivation.soothing_system": "你是考研学习安抚和最小行动助手，不做心理诊断，只给可执行小动作。",
}


class PromptRegistry:
    def __init__(self, prompt_dir: Optional[Path] = None):
        self.prompt_dir = prompt_dir or PROMPTS_DIR

    def get(self, name: str, version: str = "default") -> str:
        if name == "nightly_memory_update":
            path = self.prompt_dir / NIGHTLY_MEMORY_PROMPT_PATH.name
            if path.exists():
                return path.read_text(encoding="utf-8")

        key = f"{name}.{version}"
        if key in DEFAULT_PROMPTS:
            return DEFAULT_PROMPTS[key]
        if name in DEFAULT_PROMPTS:
            return DEFAULT_PROMPTS[name]
        raise KeyError(f"Prompt not found: {name}@{version}")

    def render(self, name: str, variables: Optional[Dict[str, object]] = None) -> str:
        template = self.get(name)
        variables = variables or {}
        return template.format(**variables)


def get_nightly_memory_prompt() -> str:
    return PromptRegistry().get("nightly_memory_update")

