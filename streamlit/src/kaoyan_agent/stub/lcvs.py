from .memory.store import (
    AbstractMemoryStore,
    AbstractProblemStore,
    AbstractDiaryStore,
)

from .memory.type import (
    Memory,
    Problem,
    Diary,
)

from typing import Any
from langchain_community.vectorstores import LanceDB
from langchain.embeddings import Embeddings
from langchain_core.documents import Document


class LCVSMemoryStore(AbstractMemoryStore):
    def __init__(
        self,
        embedding: Embeddings,
        *,
        uri: str = "/vectors",
        table_name: str = "memory",
    ) -> None:
        self.vector_store = LanceDB(
            embedding=embedding,
            uri=uri,
            table_name=table_name,
        )

    def add(
        self,
        items: list[Memory],
    ) -> None:
        documents: list[Document] = [
            Document(
                x["content"],
                id=x["uuid"],
                metadata=x,
            )
            for x in items
        ]

        self.vector_store.add_documents(documents)

    def delete(
        self,
        ids: list[str],
    ) -> None:
        self.vector_store.delete(ids)

    def get_all(self) -> list[Memory]:
        return []

    def similarity_search(
        self,
        query: str,
        top_k: int,
        filter: dict[str, Any],
    ) -> list[tuple[Memory, float]]:
        return [
            (x[0]["metadata"], x[1])  # type: ignore
            for x in self.vector_store.similarity_search_with_relevance_scores(
                query,
                top_k,
                filter=filter,
            )
        ]


class LCVSProblemStore(AbstractProblemStore):
    def __init__(
        self,
        embedding: Embeddings,
        *,
        uri: str = "/vectors",
        table_name: str = "problem",
    ) -> None:
        self.vector_store = LanceDB(
            embedding=embedding,
            uri=uri,
            table_name=table_name,
        )

    def add(
        self,
        items: list[Problem],
    ) -> None:
        documents: list[Document] = [
            Document(
                x["description"],
                id=x["uuid"],
                metadata=x,
            )
            for x in items
        ]

        self.vector_store.add_documents(documents)

    def delete(
        self,
        ids: list[str],
    ) -> None:
        self.vector_store.delete(ids)

    def get_all(self) -> list[Problem]:
        return []

    def similarity_search(
        self,
        query: str,
        top_k: int,
        filter: dict[str, Any],
    ) -> list[tuple[Problem, float]]:
        return [
            (x[0]["metadata"], x[1])  # type: ignore
            for x in self.vector_store.similarity_search_with_relevance_scores(
                query,
                top_k,
                filter=filter,
            )
        ]


class LCVSDiaryStore(AbstractDiaryStore):
    def __init__(
        self,
        embedding: Embeddings,
        *,
        uri: str = "/vectors",
        table_name: str = "diary",
    ) -> None:
        self.vector_store = LanceDB(
            embedding=embedding,
            uri=uri,
            table_name=table_name,
        )

    def add(
        self,
        items: list[Diary],
    ) -> None:
        documents: list[Document] = [
            Document(
                x["summary"]["summary"],
                id=x["add_at"],
                metadata=x,
            )
            for x in items
        ]

        self.vector_store.add_documents(documents)

    def delete(
        self,
        ids: list[str],
    ) -> None:
        self.vector_store.delete(ids)

    def get_all(self) -> list[Diary]:
        return []

    def similarity_search(
        self,
        query: str,
        top_k: int,
        filter: dict[str, Any],
    ) -> list[tuple[Diary, float]]:
        return [
            (x[0]["metadata"], x[1])  # type: ignore
            for x in self.vector_store.similarity_search_with_relevance_scores(
                query,
                top_k,
                filter=filter,
            )
        ]
