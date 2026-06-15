"""分数趋势分析 Agent"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.services.llm_client import run_structured_agent


class ScoreAnalysis(BaseModel):
    """分数分析结果"""
    trend: str = Field(description="趋势方向: improving / stable / declining / fluctuating")
    suggestion: str = Field(description="针对该科目的具体建议，30-80字")
    risk_level: str = Field(description="风险等级: low / medium / high")
    focus_points: List[str] = Field(default_factory=list, description="需要关注的知识点或方面")


class ScoreAnalyzerAgent:
    """分析分数趋势并给出建议"""
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings
    
    def analyze(self, subject: str, records: List[Dict[str, Any]]) -> Optional[ScoreAnalysis]:
        """分析单科分数趋势"""
        
        if len(records) < 2:
            return None
        
        # 准备数据
        scores = []
        dates = []
        for r in records:
            score = r.get('score', 0)
            full = r.get('full_score', 100)
            scores.append(round(score / full * 100, 1))  # 转为百分制
            dates.append(r.get('exam_date', '')[:10])
        
        recent = scores[-3:] if len(scores) >= 3 else scores
        overall_trend = self._calc_trend(scores)
        
        prompt = f"""
科目：{subject}
历次考试成绩（百分制）：{scores}
考试日期：{dates}
整体趋势：{overall_trend}
最近3次成绩：{recent}

请分析这个科目的学习趋势，并给出具体的学习建议。

输出格式：
{{
    "trend": "improving/stable/declining/fluctuating",
    "suggestion": "具体建议，30-80字",
    "risk_level": "low/medium/high",
    "focus_points": ["需要关注的点1", "点2"]
}}
"""
        
        system_prompt = """你是考研学习分析助手。根据用户的模考成绩趋势，给出有针对性的学习建议。建议要具体、可执行，不要说空话。"""
        
        try:
            result = run_structured_agent(
                ScoreAnalysis,
                prompt,
                system_prompt=system_prompt,
                settings=self.settings,
                temperature=0.3,
            )
            return result
        except Exception:
            return self._fallback_analysis(subject, overall_trend, recent)
    
    def _calc_trend(self, scores: List[float]) -> str:
        """简单计算趋势"""
        if len(scores) < 2:
            return "unknown"
        
        first = scores[0]
        last = scores[-1]
        
        if last - first > 5:
            return "improving"
        elif first - last > 5:
            return "declining"
        elif max(scores) - min(scores) > 10:
            return "fluctuating"
        else:
            return "stable"
    
    def _fallback_analysis(self, subject: str, trend: str, recent: List[float]) -> ScoreAnalysis:
        """降级分析"""
        if trend == "declining":
            suggestion = f"{subject}成绩呈下降趋势，建议回顾最近几次考试的错题，重点复习薄弱章节，增加针对性练习。"
            risk = "high"
            focus = ["错题复盘", "薄弱章节"]
        elif trend == "improving":
            suggestion = f"{subject}成绩在提升，保持当前复习节奏，可以适当挑战更高难度的题目。"
            risk = "low"
            focus = ["保持节奏", "适当拔高"]
        elif trend == "fluctuating":
            suggestion = f"{subject}成绩波动较大，建议找出稳定得分的题型，先巩固基础再追求难题。"
            risk = "medium"
            focus = ["基础巩固", "稳定题型"]
        else:
            suggestion = f"{subject}成绩稳定，建议在保持的基础上，针对易错点进行专项突破。"
            risk = "medium"
            focus = ["专项突破", "查漏补缺"]
        
        return ScoreAnalysis(
            trend=trend,
            suggestion=suggestion,
            risk_level=risk,
            focus_points=focus
        )
