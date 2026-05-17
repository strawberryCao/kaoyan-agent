from typing import Dict, List, Optional

from config import Settings
from db.database import get_messages_by_session
from services.llm_client import LLMClient, LLMConfigError


class ChatAgent:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings

    def get_recent_chat_messages(
        self, session_id: int, limit: int = 20
    ) -> List[Dict[str, str]]:
        messages = get_messages_by_session(session_id, limit=limit)
        return [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if message["role"] in {"user", "assistant"}
        ]

    def respond(self, session_id: int, limit: int = 20) -> str:
        try:
            return LLMClient(self.settings).chat(
                self.get_recent_chat_messages(session_id, limit=limit)
            )
        except LLMConfigError as exc:
            return f"LLM is not configured: {exc}"
        except Exception as exc:
            return f"LLM request failed: {exc}"
