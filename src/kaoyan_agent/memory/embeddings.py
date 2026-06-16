import json
import math
from typing import Any, Iterable, List
from urllib import error, request

from kaoyan_agent.core.settings import Settings, get_settings


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left or [])
    right_values = list(right or [])
    if not left_values or not right_values or len(left_values) != len(right_values):
        return 0.0

    dot = sum(a * b for a, b in zip(left_values, right_values))
    left_norm = math.sqrt(sum(a * a for a in left_values))
    right_norm = math.sqrt(sum(b * b for b in right_values))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class EmbeddingClient:
    """OpenAI-compatible embedding API client with no hard runtime dependency.

    SiliconFlow and Voyage both expose an embeddings endpoint that returns
    ``data[].embedding``. When the API key is absent or the request fails, the
    client returns empty vectors so callers can fall back to lexical scoring.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.last_status = "not_called"
        self.last_error = ""

    @property
    def provider(self) -> str:
        return self.settings.embedding_provider or "siliconflow"

    @property
    def model(self) -> str:
        return self.settings.embedding_model or "BAAI/bge-m3"

    def encode(self, text: str) -> List[float]:
        vectors = self.encode_many([text])
        return vectors[0] if vectors else []

    def encode_many(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [(text or "").strip() for text in texts]
        if not clean_texts:
            self.last_status = "skipped"
            self.last_error = ""
            return []
        if not self.settings.embedding_api_key:
            self.last_status = "disabled"
            self.last_error = "EMBEDDING_API_KEY is missing"
            return [[] for _ in clean_texts]

        try:
            payload = self._build_payload(clean_texts)
            response = self._post_json(self.endpoint(), payload)
            vectors = self._parse_vectors(response, len(clean_texts))
        except Exception as exc:
            self.last_status = "failed"
            self.last_error = str(exc)
            return [[] for _ in clean_texts]

        self.last_status = "success"
        self.last_error = ""
        return vectors

    def endpoint(self) -> str:
        base_url = (self.settings.embedding_base_url or "").rstrip("/")
        if not base_url:
            base_url = "https://api.siliconflow.cn/v1"
        return f"{base_url}/embeddings"

    def status_metadata(self) -> dict[str, Any]:
        return {
            "embedding_provider": self.provider,
            "embedding_model": self.model,
            "embedding_status": self.last_status,
            "embedding_error": self.last_error,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.settings.embedding_base_url or "https://api.siliconflow.cn/v1",
            "configured": bool(self.settings.embedding_api_key),
            "available": bool(self.settings.embedding_api_key),
            "last_status": self.last_status,
            "last_error": self.last_error if self.last_error else (
                "" if self.settings.embedding_api_key else "EMBEDDING_API_KEY is missing"
            ),
        }

    def _build_payload(self, texts: list[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts if len(texts) > 1 else texts[0],
        }
        if self.provider.lower() == "voyage":
            payload["input_type"] = "document"
        return payload

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.embedding_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(
                http_request,
                timeout=float(self.settings.embedding_timeout_seconds),
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"embedding API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"embedding API request failed: {exc}") from exc

    def _parse_vectors(self, response: dict[str, Any], expected_count: int) -> list[list[float]]:
        data = response.get("data")
        if not isinstance(data, list):
            raise ValueError("embedding API response missing data list")

        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list):
                vectors.append([])
                continue
            vectors.append([float(value) for value in embedding])

        while len(vectors) < expected_count:
            vectors.append([])
        return vectors[:expected_count]
