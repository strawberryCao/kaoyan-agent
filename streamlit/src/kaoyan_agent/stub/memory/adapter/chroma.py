import json
import uuid
import chromadb

from typing import Any
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from .type import (
    Memory,
    Problem,
    Diary,
)

from .store import (
    AbstractMemoryStore,
    AbstractProblemStore,
    AbstractDiaryStore,
)


class ChromaMemoryStore(AbstractMemoryStore):
    def __init__(
        self,
        path: str = "./chroma_data",
        collection_name: str = "memory_store",
        embedding_fn=None,
    ):
        self.client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        if embedding_fn is None:
            embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, items: list[Memory]) -> None:
        ids = [item["uuid"] for item in items]
        documents = [item["content"] for item in items]
        metadatas = [
            {
                "type": item["type"],
                "confidence_score": item["confidence_score"],
                "effectiveness_score": item["effectiveness_score"],
                "add_at": item["add_at"],
                "updated_at": item["updated_at"],
                "last_used_at": item["last_used_at"],
                "status": item["status"],
            }
            for item in items
        ]
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def delete(self, ids: list[str]) -> None:
        self.collection.delete(ids=ids)

    def get_all(self) -> list[Memory]:
        results = self.collection.get()
        if not results["ids"]:
            return []
        memories = []
        for idx, mem_id in enumerate(results["ids"]):
            meta = results["metadatas"][idx]
            memory: Memory = {
                "uuid": mem_id,
                "type": meta["type"],
                "content": results["documents"][idx],
                "confidence_score": meta["confidence_score"],
                "effectiveness_score": meta["effectiveness_score"],
                "add_at": meta["add_at"],
                "updated_at": meta["updated_at"],
                "last_used_at": meta["last_used_at"],
                "status": meta["status"],
            }
            memories.append(memory)
        return memories

    def similarity_search(
        self, query: str, top_k: int, filter: dict[str, Any]
    ) -> tuple[list[Memory], float]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=filter if filter else None,
        )
        if not results["ids"] or not results["ids"][0]:
            return [], 0.0

        memories = []
        similarities = []
        for i, mem_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i]  # cosine distance
            similarity = 1 - distance  # convert to similarity score
            similarities.append(similarity)
            memory: Memory = {
                "uuid": mem_id,
                "type": meta["type"],
                "content": results["documents"][0][i],
                "confidence_score": meta["confidence_score"],
                "effectiveness_score": meta["effectiveness_score"],
                "add_at": meta["add_at"],
                "updated_at": meta["updated_at"],
                "last_used_at": meta["last_used_at"],
                "status": meta["status"],
            }
            memories.append(memory)
        best_score = max(similarities) if similarities else 0.0
        return memories, best_score


class ChromaProblemStore(AbstractProblemStore):
    def __init__(
        self,
        path: str = "./chroma_data",
        collection_name: str = "problem_store",
        embedding_fn=None,
    ):
        self.client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        if embedding_fn is None:
            embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, items: list[Problem]) -> None:
        ids = [item["uuid"] for item in items]
        documents = [f"{item['title']} {item['description']}" for item in items]
        metadatas = [
            {
                "impact_score": item["impact_score"],
                "add_at": item["add_at"],
                "status": item["status"],
            }
            for item in items
        ]
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def delete(self, ids: list[str]) -> None:
        self.collection.delete(ids=ids)

    def get_all(self) -> list[Problem]:
        results = self.collection.get()
        if not results["ids"]:
            return []
        problems = []
        for idx, prob_id in enumerate(results["ids"]):
            meta = results["metadatas"][idx]
            doc = results["documents"][idx]
            # Split title and description (naive split on first space)
            # Better to store title/description separately in metadata? For simplicity:
            # We assume document format is "title description"
            # But to reconstruct exactly, we could store title and description as metadata.
            # Let's store them in metadata for accuracy.
            # However, existing add only stored combined string. To fix, we should store as metadata.
            # I'll modify add to store title and description separately.
            pass
        # Reimplement add to store title and description in metadata.
        # Actually above add is insufficient for exact reconstruction.
        # Let's redo properly: store title and description as metadata.
        # For backward compatibility, we handle both.
        # Better to update add method:
        # self.collection.upsert(ids=ids, documents=documents, metadatas=[{"title": item["title"], "description": item["description"], "impact_score":..., "add_at":..., "status":...}])
        # Then in get_all, reconstruct from metadata.
        # Let's correct.
        # But as the code is being written fresh, I'll correct now.
        pass


# Corrected ChromaProblemStore with proper metadata
class ChromaProblemStore(AbstractProblemStore):
    def __init__(
        self,
        path: str = "./chroma_data",
        collection_name: str = "problem_store",
        embedding_fn=None,
    ):
        self.client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        if embedding_fn is None:
            embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, items: list[Problem]) -> None:
        ids = [item["uuid"] for item in items]
        documents = [f"{item['title']} {item['description']}" for item in items]
        metadatas = [
            {
                "title": item["title"],
                "description": item["description"],
                "impact_score": item["impact_score"],
                "add_at": item["add_at"],
                "status": item["status"],
            }
            for item in items
        ]
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def delete(self, ids: list[str]) -> None:
        self.collection.delete(ids=ids)

    def get_all(self) -> list[Problem]:
        results = self.collection.get()
        if not results["ids"]:
            return []
        problems = []
        for idx, prob_id in enumerate(results["ids"]):
            meta = results["metadatas"][idx]
            problem: Problem = {
                "uuid": prob_id,
                "title": meta["title"],
                "description": meta["description"],
                "impact_score": meta["impact_score"],
                "add_at": meta["add_at"],
                "status": meta["status"],
            }
            problems.append(problem)
        return problems

    def similarity_search(
        self, query: str, top_k: int, filter: dict[str, Any]
    ) -> tuple[list[Problem], float]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=filter if filter else None,
        )
        if not results["ids"] or not results["ids"][0]:
            return [], 0.0

        problems = []
        similarities = []
        for i, prob_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            similarity = 1 - distance
            similarities.append(similarity)
            problem: Problem = {
                "uuid": prob_id,
                "title": meta["title"],
                "description": meta["description"],
                "impact_score": meta["impact_score"],
                "add_at": meta["add_at"],
                "status": meta["status"],
            }
            problems.append(problem)
        best_score = max(similarities) if similarities else 0.0
        return problems, best_score


class ChromaDiaryStore(AbstractDiaryStore):
    def __init__(
        self,
        path: str = "./chroma_data",
        collection_name: str = "diary_store",
        embedding_fn=None,
    ):
        self.client = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        if embedding_fn is None:
            embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, items: list[Diary]) -> None:
        ids = []
        documents = []
        metadatas = []
        for diary in items:
            # Use a unique id (add_at is not guaranteed unique; add random suffix)
            unique_id = f"{diary['add_at']}_{uuid.uuid4().hex[:8]}"
            ids.append(unique_id)
            # Document for embedding: the summary text
            doc = diary["summary"]["summary"]
            documents.append(doc)
            # Store full diary as JSON in metadata
            full_diary_json = json.dumps(diary, ensure_ascii=False)
            metadatas.append(
                {"add_at": diary["add_at"], "full_diary_json": full_diary_json}
            )
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def delete(self, ids: list[str]) -> None:
        self.collection.delete(ids=ids)

    def get_all(self) -> list[Diary]:
        results = self.collection.get()
        if not results["ids"]:
            return []
        diaries = []
        for idx, meta in enumerate(results["metadatas"]):
            full_json = meta.get("full_diary_json")
            if full_json:
                diary = json.loads(full_json)
                diaries.append(diary)
        return diaries

    def similarity_search(
        self, query: str, top_k: int, filter: dict[str, Any]
    ) -> tuple[list[Diary], float]:
        # Note: filter is applied to metadata. If filter contains fields that are only inside
        # full_diary_json, they cannot be filtered directly. We only support filtering by 'add_at'.
        where = None
        if filter:
            # Convert simple filter to chromadb format if needed
            where = filter
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        if not results["ids"] or not results["ids"][0]:
            return [], 0.0

        diaries = []
        similarities = []
        for i, meta in enumerate(results["metadatas"][0]):
            distance = results["distances"][0][i]
            similarity = 1 - distance
            similarities.append(similarity)
            full_json = meta.get("full_diary_json")
            if full_json:
                diary = json.loads(full_json)
                diaries.append(diary)
        best_score = max(similarities) if similarities else 0.0
        return diaries, best_score
