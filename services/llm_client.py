from typing import Dict, List, Optional

from openai import OpenAI

from config import Settings, get_settings


DEFAULT_SYSTEM_PROMPT = (
    "You are ChatAgent for a postgraduate exam preparation assistant. "
    "Answer the user directly and practically. "
    "Normal chat does not proactively use long-term memory, files, or web search "
    "unless that information is explicitly provided in the current conversation. "
    "Answer in the user's language."
)


class LLMConfigError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        if not self.settings.llm_api_key:
            raise LLMConfigError("LLM_API_KEY is missing. Create a .env file first.")

        client_kwargs = {"api_key": self.settings.llm_api_key}
        if self.settings.llm_base_url:
            client_kwargs["base_url"] = self.settings.llm_base_url

        self.client = OpenAI(**client_kwargs)
        self.model = self.settings.llm_model

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        temperature: float = 0.3,
    ) -> str:
        request_messages = []
        if system_prompt:
            request_messages.append({"role": "system", "content": system_prompt})
        request_messages.extend(messages)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=request_messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
