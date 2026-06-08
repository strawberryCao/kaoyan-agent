from .type import *

import json

from typing import Any
from langchain.messages import HumanMessage, SystemMessage
from langchain.chat_models import BaseChatModel


def flatten_messages(messages: list[Message]) -> str:
    return "\n\n".join([f"{role}: {text}" for role, text in messages])


def flatten_memories(memories: list[Memory]) -> str:
    return "\n\n".join([json.dumps(x) for x in memories])


def flatten_problems(problems: list[Problem]) -> str:
    return "\n\n".join([json.dumps(x) for x in problems])


def call_structured_model(
    model: BaseChatModel,
    prompt: str,
    content: str,
    schema: Any,
) -> Any:
    structured_model = model.with_structured_output(schema)  # type: ignore
    retried: int = 0
    while retried <= 3:
        try:
            response = structured_model.invoke(  # type: ignore
                [SystemMessage(prompt), HumanMessage(content)]
            )
            return response  # type: ignore
        except Exception as e:
            print(e)
            retried += 1

    return None
