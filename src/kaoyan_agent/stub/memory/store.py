from .type import *

from typing import Any
from abc import ABC, abstractmethod


class AbstractMemoryStore(ABC):
    @abstractmethod
    def add(self, items: list[Memory]) -> None:
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        pass

    @abstractmethod
    def get_all(self) -> list[Memory]:
        pass

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        top_k: int,
        filter: dict[str, Any],
    ) -> list[tuple[Memory, float]]:
        pass


class AbstractProblemStore(ABC):
    @abstractmethod
    def add(self, items: list[Problem]) -> None:
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        pass

    @abstractmethod
    def get_all(self) -> list[Problem]:
        pass

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        top_k: int,
        filter: dict[str, Any],
    ) -> list[tuple[Problem, float]]:
        pass


class AbstractDiaryStore(ABC):
    @abstractmethod
    def add(self, items: list[Diary]) -> None:
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        pass

    @abstractmethod
    def get_all(self) -> list[Diary]:
        pass

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        top_k: int,
        filter: dict[str, Any],
    ) -> list[tuple[Diary, float]]:
        pass
