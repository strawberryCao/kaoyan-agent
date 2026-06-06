import json
from typing import Any, Dict, Iterable, Optional


def response_candidates(raw_response: str) -> list[str]:
    """从 LLM 原始文本中提取可能是 JSON 对象的候选片段。

    LLM 有时会返回纯 JSON、Markdown 代码块，或在解释文字中夹一段 JSON；
    调用方会按候选顺序尝试解析，失败时再走 fallback。
    """

    text = (raw_response or "").strip()
    candidates = [text]

    if text.startswith("```"):
        # 兼容 ```json ... ``` 这种常见模型输出格式。
        lines = text.splitlines()
        fenced = "\n".join(lines[1:])
        if fenced.rstrip().endswith("```"):
            fenced = fenced.rstrip()
            fenced = fenced[: fenced.rfind("```")]
        candidates.append(fenced.strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        # 兼容“解释文字 + JSON + 解释文字”的输出，只截取最外层对象。
        candidates.append(text[start : end + 1])

    return [candidate for candidate in candidates if candidate]


def parse_json_object(raw_response: str) -> Optional[Dict[str, Any]]:
    """解析模型输出中的 JSON 对象；无法解析时返回 None 而不是抛异常。"""

    for candidate in response_candidates(raw_response):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def require_keys(value: Dict[str, Any], required_keys: Iterable[str]) -> bool:
    return all(key in value for key in required_keys)


def json_dumps(value: Any, fallback: Any) -> str:
    try:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)
    except TypeError:
        return json.dumps(fallback, ensure_ascii=False)


def json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except json.JSONDecodeError:
        return fallback

