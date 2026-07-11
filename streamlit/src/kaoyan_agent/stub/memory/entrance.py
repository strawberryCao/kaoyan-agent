from .store import *
from .type import *
from .utils import *

from .nightly import summarize_diary
from .retrieve import retrieve_memories, retrieve_problems

from langchain.chat_models import BaseChatModel


class MemoryEntrance:
    def __init__(
        self,
        model: BaseChatModel,
        memory_store: AbstractMemoryStore,
        problem_store: AbstractProblemStore,
        diary_store: AbstractDiaryStore,
    ) -> None:
        self.model = model
        self.memory_store = memory_store
        self.problem_store = problem_store
        self.diary_store = diary_store

    def operate_nightly(
        self,
        messages: list[Message],
    ):
        diary: Diary = summarize_diary(
            self.model,
            messages,
            self.memory_store.get_all(),
            self.problem_store.get_all(),
        )

        self.memory_store.delete([x["uuid"] for x in diary["updated_memories"]])
        self.memory_store.add(diary["updated_memories"])
        self.memory_store.add(diary["new_memories"])

        self.problem_store.delete([x["uuid"] for x in diary["updated_problems"]])
        self.problem_store.add(diary["updated_problems"])
        self.problem_store.add(diary["new_problems"])

        self.diary_store.add([diary])

    def retrieve_memories(
        self,
        messages: list[Message],
        top_k: int = 4,
    ) -> list[Memory]:
        return retrieve_memories(
            self.model,
            self.memory_store,
            messages,
            top_k,
        )

    def retrieve_problems(
        self,
        messages: list[Message],
        top_k: int = 4,
    ) -> list[Problem]:
        return retrieve_problems(
            self.model,
            self.problem_store,
            messages,
            top_k,
        )
