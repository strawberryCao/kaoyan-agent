from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.services.embedding_client import EmbeddingClient


class ChromaVectorStore:
    """Real Chroma vector index for memories and problems.

    SQLite remains the source of truth. Chroma is an index backend: it can be
    rebuilt from SQLite by the backfill script, and embedding failures are
    reported explicitly instead of being replaced with fake vectors.
    """

    memory_collection_name = "memories"
    problem_collection_name = "problems"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        collection: Any = None,
        collections: Optional[Dict[str, Any]] = None,
        client: Any = None,
    ):
        self.settings = settings or get_settings()
        self.embedding_client = embedding_client or EmbeddingClient(self.settings)
        self._client = client
        self._collections: Dict[str, Any] = dict(collections or {})
        if collection is not None:
            # Backward-compatible test hook. When a single collection is injected
            # we only query that collection, avoiding duplicate fake results.
            self._collections[self.memory_collection_name] = collection
        self._last_error = ""

    def upsert_memory(
        self,
        memory: Dict[str, Any] | int,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if isinstance(memory, dict):
            memory_id = memory.get("id")
            document = str(memory.get("content") or "")
            item_metadata = {
                "project_id": memory.get("project_id"),
                "memory_type": memory.get("memory_type"),
                "status": memory.get("status"),
                "updated_at": memory.get("updated_at") or memory.get("created_at"),
                "effectiveness_score": memory.get("effectiveness_score") or 0.0,
                "heat_score": 0.05,
                **dict(metadata or {}),
            }
            existing_embedding = memory.get("embedding") or []
        else:
            memory_id = memory
            document = str(content or "")
            item_metadata = dict(metadata or {})
            existing_embedding = item_metadata.pop("embedding", [])

        return self._upsert(
            collection_name=self.memory_collection_name,
            source_type="memory",
            source_id=memory_id,
            document=document,
            metadata=item_metadata,
            existing_embedding=existing_embedding,
        )

    def upsert_problem(
        self,
        problem: Dict[str, Any] | int,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if isinstance(problem, dict):
            problem_id = problem.get("id")
            document = self.problem_document(problem)
            item_metadata = {
                "project_id": problem.get("project_id"),
                "problem_type": problem.get("problem_type"),
                "subject": problem.get("subject"),
                "status": problem.get("status"),
                "updated_at": problem.get("updated_at") or problem.get("created_at"),
                "effectiveness_score": 0.0,
                "heat_score": 0.1,
                **dict(metadata or {}),
            }
            existing_embedding = problem.get("embedding") or []
        else:
            problem_id = problem
            document = str(content or "")
            item_metadata = dict(metadata or {})
            existing_embedding = item_metadata.pop("embedding", [])

        return self._upsert(
            collection_name=self.problem_collection_name,
            source_type="problem",
            source_id=problem_id,
            document=document,
            metadata=item_metadata,
            existing_embedding=existing_embedding,
        )

    def query(
        self,
        text: str,
        limit: int = 8,
        project_id: Optional[int] = None,
        top_k: Optional[int] = None,
        collection_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        query_text = (text or "").strip()
        if not query_text:
            return []
        if self.settings.vector_backend != "chroma":
            self._last_error = "VECTOR_BACKEND is not chroma"
            return []

        query_embedding = self.embedding_client.encode(query_text)
        if not query_embedding:
            self._last_error = self.embedding_client.last_error or "query embedding unavailable"
            return []

        result_limit = max(1, int(top_k or limit or 8))
        names = collection_names or self.query_collection_names()
        all_items: List[Dict[str, Any]] = []
        for name in names:
            collection = self.get_collection(name)
            if collection is None:
                continue
            where = {"project_id": project_id} if project_id is not None else None
            try:
                result = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=result_limit,
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:
                self._last_error = str(exc)
                continue
            all_items.extend(self._normalize_query_result(result, name))

        all_items.sort(key=lambda item: item.get("vector_similarity", 0.0), reverse=True)
        return all_items[:result_limit]

    def get_status(self) -> Dict[str, Any]:
        status = {
            "backend": self.settings.vector_backend or "none",
            "enabled": self.settings.vector_backend == "chroma",
            "available": False,
            "persist_dir": str(self.settings.chroma_persist_dir),
            "embedding_provider": self.settings.embedding_provider,
            "embedding_model": self.settings.embedding_model,
            "embedding_available": bool(self.settings.embedding_api_key),
            "embedding_error": "" if self.settings.embedding_api_key else "EMBEDDING_API_KEY is missing",
            "collection_names": [self.memory_collection_name, self.problem_collection_name],
            "collections": {},
            "collection_count": 0,
            "documents_count": 0,
            "error": "",
        }
        if self.settings.vector_backend != "chroma":
            status["error"] = "VECTOR_BACKEND is not chroma"
            return status

        collections: Dict[str, int] = {}
        for name in [self.memory_collection_name, self.problem_collection_name]:
            collection = self.get_collection(name)
            if collection is None:
                status["error"] = self._last_error or f"Chroma collection {name} unavailable"
                return status
            try:
                collections[name] = int(collection.count())
            except Exception as exc:
                collections[name] = 0
                status["error"] = str(exc)

        status["available"] = True
        status["collections"] = collections
        status["collection_count"] = sum(collections.values())
        status["documents_count"] = status["collection_count"]
        if not status["error"]:
            status["error"] = self._last_error
        return status

    def get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self.settings.vector_backend != "chroma":
            self._last_error = "VECTOR_BACKEND is not chroma"
            return None
        try:
            import chromadb
        except ModuleNotFoundError:
            self._last_error = "chromadb is not installed"
            return None
        try:
            persist_dir = Path(self.settings.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_dir))
            self._last_error = ""
            return self._client
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def get_collection(self, name: str = memory_collection_name) -> Any:
        if name in self._collections:
            return self._collections[name]
        client = self.get_client()
        if client is None:
            return None
        try:
            collection = client.get_or_create_collection(name)
            self._collections[name] = collection
            self._last_error = ""
            return collection
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def query_collection_names(self) -> List[str]:
        if self._collections:
            return list(self._collections.keys())
        return [self.memory_collection_name, self.problem_collection_name]

    def _upsert(
        self,
        *,
        collection_name: str,
        source_type: str,
        source_id: Any,
        document: str,
        metadata: Dict[str, Any],
        existing_embedding: List[float],
    ) -> Dict[str, Any]:
        if not source_id or not str(document or "").strip():
            return {"status": "skipped", "reason": "missing source id or document"}
        collection = self.get_collection(collection_name)
        if collection is None:
            return {"status": "unavailable", "error": self._last_error}

        embedding = existing_embedding or self.embedding_client.encode(document)
        if not embedding:
            return {
                "status": "unavailable",
                "error": self.embedding_client.last_error or "embedding unavailable",
            }

        doc_id = self.document_id(source_type, int(source_id))
        safe_metadata = self.safe_metadata(
            {
                **metadata,
                "source_type": source_type,
                "source_id": int(source_id),
            }
        )
        try:
            collection.upsert(
                ids=[doc_id],
                documents=[document],
                embeddings=[embedding],
                metadatas=[safe_metadata],
            )
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "failed", "error": str(exc)}
        return {"status": "success", "id": doc_id, "collection": collection_name}

    @classmethod
    def document_id(cls, source_type: str, source_id: int) -> str:
        return f"{source_type}:{source_id}"

    @staticmethod
    def problem_document(problem: Dict[str, Any]) -> str:
        parts = [
            str(problem.get("problem_type") or ""),
            str(problem.get("subject") or ""),
            str(problem.get("description") or ""),
            str(problem.get("root_cause") or ""),
            str(problem.get("suggested_action") or ""),
        ]
        return " | ".join(part for part in parts if part.strip())

    @staticmethod
    def safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key, value in metadata.items():
            if value is None:
                safe[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                safe[key] = value
            else:
                safe[key] = json.dumps(value, ensure_ascii=False)
        return safe

    @staticmethod
    def _normalize_query_result(result: Dict[str, Any], collection_name: str) -> List[Dict[str, Any]]:
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        items: List[Dict[str, Any]] = []
        for index, doc_id in enumerate(ids):
            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            distance = float(distances[index] or 0.0) if index < len(distances) else 0.0
            similarity = max(0.0, min(1.0, 1.0 - distance))
            source_type = str(metadata.get("source_type") or "")
            source_id = int(metadata.get("source_id") or 0)
            if not source_type and isinstance(doc_id, str) and ":" in doc_id:
                source_type, raw_source_id = doc_id.split(":", 1)
                source_id = int(raw_source_id) if raw_source_id.isdigit() else 0
            items.append(
                {
                    "id": doc_id,
                    "collection": collection_name,
                    "source_type": source_type,
                    "source_id": source_id,
                    "content": documents[index] if index < len(documents) else "",
                    "vector_similarity": round(similarity, 4),
                    "metadata": metadata,
                }
            )
        return items


VectorStore = ChromaVectorStore

