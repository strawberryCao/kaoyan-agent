"""成绩预测 Agent"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.services.llm_client import run_structured_agent


class PredictionResult(BaseModel):
    """预测结果"""
    next_score: int = Field(ge=0, le=100, description="预测的下次成绩(百分制)")
    lower_bound: int = Field(ge=0, le=100, description="预测下限")
    upper_bound: int = Field(ge=0, le=100, description="预测上限")
    confidence: int = Field(ge=0, le=100, description="预测置信度")
    suggestion: str = Field(description="提升建议")


class ScorePredictorAgent:
    """成绩预测器"""
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings
    
    def predict(self, subject: str, records: List[Dict[str, Any]]) -> Optional[PredictionResult]:
        """根据历史成绩预测下次成绩"""
        
        if len(records) < 3:
            return None
        
        # 按日期排序
        sorted_records = sorted(records, key=lambda x: x.get('exam_date', ''))
        
        # 转为百分制
        scores = []
        for r in sorted_records:
            score = r.get('score', 0)
            full = r.get('full_score', 100)
            scores.append(round(score / full * 100, 1))
        
        # 简单线性回归预测
        n = len(scores)
        x = list(range(1, n + 1))
        x_mean = sum(x) / n
        y_mean = sum(scores) / n
        
        numerator = sum((x[i] - x_mean) * (scores[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator != 0:
            slope = numerator / denominator
            intercept = y_mean - slope * x_mean
            next_x = n + 1
            simple_pred = max(0, min(100, round(slope * next_x + intercept)))
        else:
            simple_pred = round(scores[-1])
        
        # 最近3次趋势
        recent_trend = scores[-1] - scores[-3] if n >= 3 else 0
        
        prompt = f"""
科目：{subject}
历史成绩（按时间顺序，百分制）：{scores}
最近3次成绩：{scores[-3:] if n >= 3 else scores}
简单预测的下次成绩：{simple_pred}
最近趋势：{recent_trend:+}分

请预测下一次模考成绩，并给出提升建议。

输出格式：
{{
    "next_score": 预测分数(0-100),
    "lower_bound": 预测下限(0-100),
    "upper_bound": 预测上限(0-100),
    "confidence": 置信度(0-100),
    "suggestion": "提升建议"
}}
"""
        
        system_prompt = """你是考研成绩预测专家。根据用户的历史模考成绩，预测下一次成绩区间，并给出具体可执行的提升建议。"""
        
        try:
            result = run_structured_agent(
                PredictionResult,
                prompt,
                system_prompt=system_prompt,
                settings=self.settings,
                temperature=0.3,
            )
            return result
        except Exception:
            # 降级预测
            return PredictionResult(
                next_score=simple_pred,
                lower_bound=max(0, simple_pred - 10),
                upper_bound=min(100, simple_pred + 10),
                confidence=60,
                suggestion="保持当前复习节奏，重点突破薄弱环节"
            )
