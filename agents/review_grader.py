"""复刷批改 Agent - 评估用户的复刷结果"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.services.llm_client import run_structured_agent


class GradingResult(BaseModel):
    """批改结果"""
    is_correct: int = Field(description="0: 错误, 1: 正确, -1: 部分正确")
    feedback: str = Field(description="批改反馈，50-150字")
    correct_answer_hint: str = Field(default="", description="正确思路提示")
    confidence_suggestion: int = Field(ge=0, le=100, description="建议的用户自评掌握度")
    mastery_score: int = Field(default=0, ge=0, le=100, description="建议的掌握度分数(0-100)")


class ReviewGraderAgent:
    """复刷批改器"""
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings
    
    def grade(
        self,
        question: str,           # 用户原始问题
        hint: str,               # 复刷提示内容
        user_answer: str,        # 用户的回答/理解
        reference: str = "",     # 可选的参考答案提示
    ) -> GradingResult:
        """批改用户的复刷结果"""
        
        prompt = f"""
【用户的问题/错题】
{question}

【复刷提示】
{hint}

【用户的回答/理解】
{user_answer}

请评估用户的回答是否正确，并给出具体反馈。

评估标准：
- 如果用户完全理解并正确回答：is_correct = 1
- 如果用户部分正确但有遗漏或偏差：is_correct = -1
- 如果用户完全错误或没理解：is_correct = 0

反馈要求：
1. 肯定用户做得好的地方
2. 指出不足或错误
3. 给出改进建议
4. 不要直接给完整答案，而是给思路提示

输出格式：
{{
    "is_correct": 0/1/-1,
    "feedback": "批改反馈",
    "correct_answer_hint": "正确思路提示",
    "confidence_suggestion": 0-100 建议掌握度
}}
"""
        
        system_prompt = """你是考研复刷批改助手。用户根据复刷提示提交了自己的理解或答案。请温柔地批改，给出建设性反馈，不要说教。"""
        
        try:
            result = run_structured_agent(
                GradingResult,
                prompt,
                system_prompt=system_prompt,
                settings=self.settings,
                temperature=0.3,
            )
            return result
        except Exception as e:
            return self._fallback_grade(user_answer)
    
    def _fallback_grade(self, user_answer: str) -> GradingResult:
        """降级批改"""
        return GradingResult(
            is_correct=0,
            feedback="由于系统繁忙，无法详细批改。建议你对照参考答案检查一下，或者重新描述你的理解。",
            correct_answer_hint="再仔细思考一下这个知识点的核心概念",
            confidence_suggestion=50
        )

    # 在 GradingResult 中添加 mastery_score 字段
    # 修改类定义
