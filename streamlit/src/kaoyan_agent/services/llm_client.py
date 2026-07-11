import base64
from typing import Any, Dict, List, Optional, Type
import json
from kaoyan_agent.core.json_parser import parse_json_object
from pydantic import BaseModel

from kaoyan_agent.core.settings import Settings, get_settings
from langchain.agents import create_agent



LANGCHAIN_MISSING_MESSAGE = (
    "The langchain package is not installed. "
    "Install langchain, langchain-deepseek, and langchain-openai."
)


class LLMConfigError(RuntimeError):
    pass


def create_langchain_model(
    settings: Optional[Settings] = None,
    temperature: float = 0.3,
) -> Any:
    """Create the project ChatModel through LangChain providers only."""

    settings = settings or get_settings()
    if not settings.llm_api_key:
        raise LLMConfigError("LLM_API_KEY is missing. Create a .env file first.")

    try:
        from langchain_deepseek import ChatDeepSeek

        kwargs: Dict[str, Any] = {
            "api_key": settings.llm_api_key,
            "model": settings.llm_model,
            "temperature": temperature,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatDeepSeek(**kwargs)
    except ModuleNotFoundError as deepseek_error:
        if deepseek_error.name != "langchain_deepseek":
            raise LLMConfigError(
                f"langchain-deepseek dependency is incomplete: {deepseek_error}"
            ) from deepseek_error

    try:
        from langchain_openai import ChatOpenAI

        kwargs = {
            "api_key": settings.llm_api_key,
            "model": settings.llm_model,
            "temperature": temperature,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatOpenAI(**kwargs)
    except ModuleNotFoundError as openai_error:
        if openai_error.name != "langchain_openai":
            raise LLMConfigError(
                f"langchain-openai dependency is incomplete: {openai_error}"
            ) from openai_error
        raise LLMConfigError(
            "No LangChain chat model provider is installed. "
            "Install langchain-deepseek or langchain-openai."
        ) from openai_error


def _build_agent(
    *,
    system_prompt: str,
    settings: Optional[Settings],
    temperature: float,
    tools: Optional[List[Any]],
    response_format: Optional[Type[BaseModel]] = None,
) -> Any:
    """Single place that wires a LangChain agent: provider model + create_agent.

    Raises if the langchain package is unavailable so callers can fall back.
    """

    if create_agent is None:
        raise LLMConfigError(LANGCHAIN_MISSING_MESSAGE)

    llm = create_langchain_model(settings, temperature=temperature)
    kwargs: Dict[str, Any] = {
        "model": llm,
        "tools": tools or [],
        "system_prompt": system_prompt,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    return create_agent(**kwargs)


def _extract_final_text(response: Any) -> str:
    """Pull the final assistant text out of a LangChain agent response."""

    if not isinstance(response, dict):
        return str(response or "").strip()

    messages = response.get("messages") or []
    if not messages:
        return ""

    final_message = messages[-1]
    content = getattr(final_message, "content", "")
    if content:
        return str(content).strip()
    if isinstance(final_message, dict):
        return str(final_message.get("content") or "").strip()
    return str(final_message or "").strip()


def run_structured_agent(
    response_format: Type[BaseModel],
    user_message: str,
    *,
    system_prompt: str,
    settings: Optional[Settings] = None,
    temperature: float = 0.2,
    tools: Optional[List[Any]] = None,
) -> BaseModel:
    """兼容 DeepSee接口的结构化输出调用。
    不直接把 Pydantic 模型作为 response_format 传给模型 而是让模型输出json再进行pydantic校验。
    """

    schema_text = json.dumps(
        response_format.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    json_user_message = (
        f"{user_message}\n\n"
        "请严格按照以下要求输出：\n"
        "1. 只输出一个 JSON 对象。\n"
        "2. 不要输出 Markdown 代码块。\n"
        "3. 不要输出解释性文字。\n"
        "4. 不要在 JSON 前后添加任何额外内容。\n"
        "5. JSON 字段必须符合下面的 schema。\n\n"
        f"{schema_text}"
    )

    agent = _build_agent(
        system_prompt=system_prompt,
        settings=settings,
        temperature=temperature,
        tools=tools,
        response_format=None,
    )

    response = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": json_user_message,
                }
            ]
        }
    )

    raw_text = _extract_final_text(response)
    parsed = parse_json_object(raw_text)

    if parsed is None:
        raise ValueError(
            "LLM response is not a valid JSON object. "
            f"Raw response: {raw_text[:500]}"
        )

    return response_format.model_validate(parsed)

def run_structured_vision_agent(
    response_format: Type[BaseModel],
    prompt: str,
    image_bytes: bytes,
    mime_type: str,
    *,
    system_prompt: str,
    settings: Optional[Settings] = None,
    temperature: float = 0.2,
) -> BaseModel:
    """Structured multimodal call for camera snapshots.

    The image is passed as an in-memory data URL. Providers without multimodal
    or structured-output support raise so callers can fall back safely.
    """

    settings = settings or get_settings()
    if not supports_vision_model(settings):
        raise LLMConfigError(f"Model does not support image_url vision messages: {settings.llm_model}")

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ModuleNotFoundError as exc:
        raise LLMConfigError(LANGCHAIN_MISSING_MESSAGE) from exc

    llm = create_langchain_model(settings, temperature=temperature)
    if not hasattr(llm, "with_structured_output"):
        raise ValueError("Current LangChain model does not support structured output.")

    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded_image}"
    structured_llm = llm.with_structured_output(response_format)
    response = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            ),
        ]
    )
    return response_format.model_validate(response)


def supports_vision_model(settings: Optional[Settings] = None) -> bool:
    settings = settings or get_settings()
    model = (settings.llm_model or "").lower()
    if not model:
        return False
    if "deepseek" in model:
        return "vision" in model or "vl" in model
    known_vision_markers = (
        "gpt-4o",
        "gpt-4.1",
        "gpt-5",
        "o3",
        "o4",
        "vision",
        "vl",
        "gemini",
        "qwen-vl",
    )
    return any(marker in model for marker in known_vision_markers)


def run_text_agent(
    messages: List[Dict[str, str]],
    *,
    system_prompt: str,
    settings: Optional[Settings] = None,
    temperature: float = 0.3,
    tools: Optional[List[Any]] = None,
) -> str:
    """Unified free-text call (used by ChatAgent). Returns the final reply text."""

    agent = _build_agent(
        system_prompt=system_prompt,
        settings=settings,
        temperature=temperature,
        tools=tools,
    )
    response = agent.invoke({"messages": messages})
    return _extract_final_text(response)


class LLMClient:
    """Lightweight holder for Settings; all model calls go through the helpers above."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        if not self.settings.llm_api_key:
            raise LLMConfigError("LLM_API_KEY is missing. Create a .env file first.")
        self.model = self.settings.llm_model
