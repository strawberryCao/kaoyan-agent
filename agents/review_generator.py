"""Review hint generator for mistake review - generates study hints, not exam questions."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.services.llm_client import run_structured_agent


class ReviewHint(BaseModel):
    """一条复刷提示"""
    hint_type: str = Field(description="concept_check / method_check / typical_mistake / formula_recall")
    content: str = Field(min_length=5, description="具体的复习提示或自查问题")
    estimated_minutes: int = Field(ge=1, le=10, description="预计完成分钟数")


class ReviewHintList(BaseModel):
    """复刷提示列表"""
    hints: List[ReviewHint] = Field(min_length=1, max_length=3)
    subject: str = Field(default="", description="所属科目")
    topic: str = Field(default="", description="所属章节或专题")
    suggestion: str = Field(default="", description="整体复习建议")


class ReviewGeneratorAgent:
    """生成复刷提示，不生成具体题目（考研题源质量要求高）"""
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings
    
    def generate_hints(
        self,
        question: str = "",
        subject: str = "",
        chapter: str = "",
        user_reason: str = "",
        from_problem: Optional[Dict[str, Any]] = None,
    ) -> ReviewHintList:
        """根据问题生成1-3条复刷提示"""
        
        context = self._build_context(question, subject, chapter, user_reason, from_problem)
        
        system_prompt = """你是考研复刷助手。根据用户的问题，生成1-3条具体的复刷提示。

提示类型说明：
- concept_check: 检查核心概念理解，如"泰勒展开的成立条件是什么？"
- method_check: 检查解题方法掌握，如"这种题型第一步应该判断什么？"
- typical_mistake: 检查易错点，如"使用洛必达前必须验证什么条件？"
- formula_recall: 检查公式记忆，如"等价无穷小替换公式中，x→0时 sin x ~ ?"

规则：
1. 不生成具体计算题，只出复习指引或自查问题
2. 每条提示5-10分钟能完成
3. 提示要具体，不要空洞的"复习这个概念"
4. 输出JSON格式，严格按照schema

输出示例：
{
  "hints": [
    {"hint_type": "concept_check", "content": "等价无穷小替换的前提条件是什么？", "estimated_minutes": 3},
    {"hint_type": "typical_mistake", "content": "做一道涉及加减项的极限题，检查是否直接替换了无穷小", "estimated_minutes": 8}
  ],
  "subject": "数学",
  "topic": "极限",
  "suggestion": "建议先复习等价无穷小的替换条件，再找2道包含加减项的极限题练习"
}"""

        try:
            result = run_structured_agent(
                ReviewHintList,
                context,
                system_prompt=system_prompt,
                settings=self.settings,
                temperature=0.3,
            )
            return result
        except Exception as e:
            return self._fallback_hints(subject, chapter)
    
    def _build_context(self, question, subject, chapter, user_reason, from_problem):
        if from_problem:
            return f"""
问题来源：问题板
科目：{from_problem.get('subject', '')}
描述：{from_problem.get('description', '')}
根因：{from_problem.get('root_cause', '')}
建议动作：{from_problem.get('suggested_action', '')}
请根据以上问题生成复刷提示。"""
        
        return f"""
用户输入的问题/错题：{question}
科目：{subject}
章节：{chapter}
用户自述原因：{user_reason}
请生成1-3条复刷提示。"""
    
    def _fallback_hints(self, subject: str, chapter: str) -> ReviewHintList:
        return ReviewHintList(
            hints=[
                ReviewHint(
                    hint_type="concept_check",
                    content="复习这个知识点的基础概念和定义，确保理解透彻",
                    estimated_minutes=5
                ),
                ReviewHint(
                    hint_type="method_check",
                    content="做一道同类型的简单题，检查解题步骤是否完整",
                    estimated_minutes=8
                )
            ],
            subject=subject or "当前科目",
            topic=chapter or "当前章节",
            suggestion="建议先复习概念，再做1-2道基础题巩固"
        )
