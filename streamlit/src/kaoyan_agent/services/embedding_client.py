"""Embedding service entrypoint.

The implementation is kept compatible with the existing memory package while
new vector-store code imports from services.
"""

from kaoyan_agent.memory.embeddings import EmbeddingClient, cosine_similarity

__all__ = ["EmbeddingClient", "cosine_similarity"]
