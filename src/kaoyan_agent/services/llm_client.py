import base64
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from kaoyan_agent.core.settings import Settings, get_settings

try:
    from langchain.agents import create_agent
except ModuleNotFoundError:
    create_agent = None



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

    llm = create_langchain_model(settings, temperature=temperature)
    if create_agent is None:
        raise LLMConfigError(LANGCHAIN_MISSING_MESSAGE)

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
    """Unified structured-output call.

    Builds the agent, invokes it, validates ``structured_response`` against the
    given Pydantic model, and returns the validated instance. Raises on missing
    or empty ``structured_response`` so each agent's local fallback can take over.
    """

    agent = _build_agent(
        system_prompt=system_prompt,
        settings=settings,
        temperature=temperature,
        tools=tools,
        response_format=response_format,
    )
    response = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    if not isinstance(response, dict) or "structured_response" not in response:
        raise ValueError("LangChain response is missing structured_response.")

    structured_response = response["structured_response"]
    if structured_response is None:
        raise ValueError("LangChain structured_response is empty.")
    return response_format.model_validate(structured_response)


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

    The image is sent as an in-memory data URL and is not persisted by this
    helper. Providers without vision support should raise so callers can fall
    back to a safe ``unknown`` result.
    """

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
