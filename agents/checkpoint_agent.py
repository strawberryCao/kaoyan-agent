import json
from typing import Any, Dict, List, Optional

from config import Settings
from services.llm_client import safe_generate_with_llm


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


def normalize_questions(value: Any, fallback: List[str]) -> List[str]:
    if not isinstance(value, list):
        return fallback
    questions = [str(item).strip() for item in value if str(item).strip()]
    if len(questions) < 4:
        return fallback
    return questions[:4]


def clamp_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def text_value(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


class CheckpointAgent:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings

    def generate_questions(self, subject: str, chapter: str) -> List[str]:
        fallback = self.build_fallback_questions(subject, chapter)
        prompt = f"""
请为考研复习章节生成闯关验收题。只返回 JSON，不要 Markdown。

要求：
- 返回字段 questions
- questions 必须包含 4 个中文问题
- 前 3 个是验收问题，第 4 个是复述题
- 问题要适合快速判断用户是否真正理解章节

科目：{subject}
章节：{chapter}
""".strip()
        raw = safe_generate_with_llm(
            prompt=prompt,
            fallback=json.dumps({"questions": fallback}, ensure_ascii=False),
            settings=self.settings,
            system_prompt="你是考研章节验收助手，负责生成短小但能暴露薄弱点的问题。",
            temperature=0.2,
        )
        parsed = parse_json_object(raw) or {"questions": fallback}
        return normalize_questions(parsed.get("questions"), fallback)

    def grade_answer(
        self,
        subject: str,
        chapter: str,
        questions: List[str],
        user_answer: str,
    ) -> Dict[str, Any]:
        fallback = self.build_fallback_grade(user_answer)
        prompt = f"""
请根据用户对章节验收题的回答给出评分。只返回 JSON，不要 Markdown。

字段：
- score: 0-100 整数
- passed: 布尔值，score >= 70 为 true
- weak_points: 字符串或字符串数组
- feedback: 中文反馈，包含下一步建议

科目：{subject}
章节：{chapter}
验收题：{json.dumps(questions, ensure_ascii=False)}
用户回答：{user_answer}
""".strip()
        raw = safe_generate_with_llm(
            prompt=prompt,
            fallback=json.dumps(fallback, ensure_ascii=False),
            settings=self.settings,
            system_prompt="你是考研章节验收评分助手，评分要直接、可执行、不过度鼓励。",
            temperature=0.2,
        )
        parsed = parse_json_object(raw) or fallback
        return self.normalize_grade(parsed, fallback)

    def build_fallback_questions(self, subject: str, chapter: str) -> List[str]:
        text = f"{subject} / {chapter}"
        if "数学" in subject and "极限" in chapter:
            return [
                "请解释无穷小和无穷大的区别。",
                "请说明为什么无界不一定是无穷大。",
                "请判断一个极限题中能否使用等价无穷小替换。",
                "请用自己的话复述极限存在的直观含义。",
            ]
        return [
            f"请说出 {text} 中最核心的 2 个概念。",
            f"请说明 {text} 常见题型的基本解题步骤。",
            f"请举一个你最容易出错的点，并说明如何避免。",
            f"请用自己的话复述 {chapter or '本章'} 的学习主线。",
        ]

    def build_fallback_grade(self, user_answer: str) -> Dict[str, Any]:
        compact_answer = "".join((user_answer or "").split())
        answer_length = len(compact_answer)
        if answer_length < 30:
            score = 50
            weak_points = "回答过短，暂时看不出关键概念和推理过程。"
        elif answer_length <= 100:
            score = 70
            weak_points = "已有基本表达，但概念边界和例题迁移还需要继续验证。"
        else:
            score = 80
            weak_points = "表达较完整，后续重点检查细节条件和规范步骤。"

        passed = score >= 70
        feedback = (
            f"fallback 评分：本次估计 {score} 分，"
            f"{'达到临时通过线' if passed else '还没有达到通过线'}。"
            "建议用同章节 1 道典型题复测薄弱点。"
        )
        return {
            "score": score,
            "passed": passed,
            "weak_points": weak_points,
            "feedback": feedback,
        }

    def normalize_grade(
        self,
        grade: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        score = clamp_score(grade.get("score", fallback["score"]))
        passed = bool(grade.get("passed", score >= 70))
        return {
            "score": score,
            "passed": passed,
            "weak_points": text_value(grade.get("weak_points") or fallback["weak_points"]),
            "feedback": str(grade.get("feedback") or fallback["feedback"]).strip(),
        }
