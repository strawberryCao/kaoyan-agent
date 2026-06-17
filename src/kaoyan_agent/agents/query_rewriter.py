from typing import Dict, List


class QueryRewriter:
    """Lightweight deterministic query rewriter.

    This keeps the original user message intact and only returns an internal
    retrieval query. A later model-based rewriter can replace it behind the
    same interface if routing quality requires it.
    """

    SHORT_REFERENCES = {"这个", "这里", "还是没懂", "刚才", "上面", "这个题"}

    def rewrite(self, user_input: str, recent_messages: List[Dict[str, str]]) -> str:
        text = user_input.strip()
        if not text:
            return text

        if len(text) <= 12 or any(token in text for token in self.SHORT_REFERENCES):
            previous = ""
            for message in reversed(recent_messages[:-1]):
                if message.get("role") == "user" and message.get("content"):
                    previous = message["content"]
                    break
            if previous:
                return f"{text}；上下文：{previous}"

        return text


