import random
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.motivation import (
    DailySignOutput,
    RandomTaskOutput,
    SoothingTaskOutput,
)
from kaoyan_agent.services.llm_client import run_structured_agent


# 内嵌 SoothingMessage Schema，避免单独文件
class SoothingMessage(BaseModel):
    """安抚签输出 - 只包含安抚语句"""
    level: str = Field(description="安抚级别: gentle/warm/energetic/calm")
    message: str = Field(min_length=10, description="安抚语句，10-50字")
    action_suggestion: str = Field(default="", description="可选：1-2个词的小动作建议")


SIGN_LEVELS = ["top", "good", "steady", "small", "calm"]


def int_between(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


class MotivationAgent:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompt_registry: Optional[PromptRegistry] = None,
    ):
        self.settings = settings
        self.prompt_registry = prompt_registry or PromptRegistry()

    def generate_daily_sign(self) -> Dict[str, Any]:
        fallback = random.choice(
            [
                {
                    "sign_level": "steady",
                    "sign_text": "保持节奏，稳步前进。",
                    "today_advice": "先完成一个15分钟的小任务。",
                    "action": "从今天任务中选最短的那个开始",
                },
                {
                    "sign_level": "good",
                    "sign_text": "稳定比速度更重要。",
                    "today_advice": "把最难的任务拆成两个小步骤。",
                    "action": "复习一道错题，标记错误原因",
                },
                {
                    "sign_level": "calm",
                    "sign_text": "少比较，多做事。",
                    "today_advice": "只关注今天实际完成的事。",
                    "action": "做一个5分钟的低门槛任务",
                },
            ]
        )
        try:
            output = self.generate_structured(
                prompt=self.prompt_registry.get("motivation.daily_sign"),
                system_prompt=self.prompt_registry.get("motivation.system"),
                response_format=DailySignOutput,
                temperature=0.7,
            )
            return self.normalize_sign(output.model_dump(), fallback)
        except Exception as exc:
            result = self.normalize_sign(fallback, fallback)
            result["generation_error"] = str(exc)
            return result

    def generate_random_task(self) -> Dict[str, Any]:
        fallback = random.choice(
            [
                {
                    "title": "复习一道最近的错题",
                    "subject": "综合",
                    "estimated_minutes": 15,
                    "reason": "短任务能帮你找回学习节奏。",
                },
                {
                    "title": "写下三个模糊的知识点",
                    "subject": "综合",
                    "estimated_minutes": 10,
                    "reason": "把模糊的地方写下来，才能针对性地解决。",
                },
                {
                    "title": "做一道当前章节的基础题",
                    "subject": "综合",
                    "estimated_minutes": 12,
                    "reason": "用小任务检验自己是否能进入学习状态。",
                },
            ]
        )
        try:
            output = self.generate_structured(
                prompt=self.prompt_registry.get("motivation.random_task"),
                system_prompt=self.prompt_registry.get("motivation.system"),
                response_format=RandomTaskOutput,
                temperature=0.5,
            )
            return self.normalize_task(output.model_dump(), fallback, max_minutes=20)
        except Exception as exc:
            result = self.normalize_task(fallback, fallback, max_minutes=20)
            result["generation_error"] = str(exc)
            return result

    def generate_soothing(self, user_state: str = "") -> Dict[str, Any]:
        """生成安抚签：安抚语句 + 可选小任务 + 小游戏入口"""
        
        # 1. 生成安抚语句
        fallback_message = {
            "level": "calm",
            "message": "累了就休息一下，这不是放弃，是为了更好地出发。",
            "action_suggestion": "深呼吸3次"
        }
        
        try:
            prompt = f"""
用户当前状态：{user_state or "状态一般"}

请生成一段温暖的安抚语句，帮助用户缓解压力、恢复能量。

要求：
1. 不要生成具体任务
2. 语句要真诚、有共鸣（10-50字）
3. 可选一个小动作建议（如深呼吸、喝口水）

输出格式：
{{
    "level": "gentle/warm/energetic/calm",
    "message": "安抚语句",
    "action_suggestion": "可选的小动作"
}}
"""
            system_prompt = "你是考研陪伴助手。用温暖的语言安抚用户，不要说教。"
            output = run_structured_agent(
                SoothingMessage,
                prompt,
                system_prompt=system_prompt,
                settings=self.settings,
                temperature=0.7,
            )
            message_data = output.model_dump()
        except Exception:
            message_data = fallback_message
        
        # 2. 生成可选的小任务（30%概率）
        import random as rand
        has_small_task = rand.random() < 0.3
        small_task = None
        
        if has_small_task:
            try:
                task_output = self.generate_structured(
                    prompt=self.prompt_registry.get("motivation.random_task"),
                    system_prompt=self.prompt_registry.get("motivation.system"),
                    response_format=RandomTaskOutput,
                    temperature=0.5,
                )
                small_task = self.normalize_task(task_output.model_dump(), {}, max_minutes=10)
            except Exception:
                small_task = {
                    "title": "站起来走走，喝口水",
                    "subject": "休息",
                    "estimated_minutes": 3,
                    "reason": "短暂的休息能让大脑恢复活力"
                }
        
        return {
            "type": "soothing",
            "message": message_data.get("message", fallback_message["message"]),
            "level": message_data.get("level", "calm"),
            "action_suggestion": message_data.get("action_suggestion", ""),
            "small_task": small_task,
            "show_games": True
        }

    def generate_soothing_task(self, user_state: str) -> Dict[str, Any]:
        """兼容原有的安抚任务接口（只返回任务）"""
        result = self.generate_soothing(user_state)
        if result.get("small_task"):
            return result["small_task"]
        return {
            "title": "给自己一点时间，放松一下",
            "subject": "休息",
            "estimated_minutes": 5,
            "reason": "累了就休息，这是为了更好地前进"
        }

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_format: Type[BaseModel],
        temperature: float,
    ) -> BaseModel:
        return run_structured_agent(
            response_format,
            prompt,
            system_prompt=system_prompt,
            settings=self.settings,
            temperature=temperature,
        )

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
            "title": str(task.get("title") or fallback.get("title", "休息一下")).strip(),
            "subject": str(task.get("subject") or fallback.get("subject", "放松")).strip(),
            "estimated_minutes": int_between(
                task.get("estimated_minutes"),
                fallback.get("estimated_minutes", 5),
                1,
                max_minutes,
            ),
            "reason": str(task.get("reason") or fallback.get("reason", "给自己一点时间")).strip(),
        }


InterventionAgent = MotivationAgent
