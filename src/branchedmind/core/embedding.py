"""Embedding providers for vector search (MatrixOne vecf32 format)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np

from branchedmind.config import settings
from branchedmind.core.exceptions import EmbeddingError


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI text-embedding-3-small provider."""

    def __init__(self) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise EmbeddingError("openai package not installed") from e
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model
        self._dims = settings.embedding_dimensions

    async def embed(self, text: str) -> list[float]:
        try:
            resp = await self._client.embeddings.create(
                input=text,
                model=self._model,
                dimensions=self._dims,
            )
            return resp.data[0].embedding
        except Exception as e:
            raise EmbeddingError(f"OpenAI embedding failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self._client.embeddings.create(
                input=texts,
                model=self._model,
                dimensions=self._dims,
            )
            return [d.embedding for d in resp.data]
        except Exception as e:
            raise EmbeddingError(f"OpenAI batch embedding failed: {e}") from e


class MockEmbedding(EmbeddingProvider):
    """Deterministic mock embedding for testing (hash-based)."""

    def __init__(self, dims: int | None = None) -> None:
        self._dims = dims or settings.embedding_dimensions

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        rng = np.random.RandomState(
            int.from_bytes(digest[:4], "big")
        )
        vec = rng.randn(self._dims).astype(np.float32)
        # Normalize to unit vector
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def get_embedding_provider() -> EmbeddingProvider:
    """Factory: return configured embedding provider."""
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        return OpenAIEmbedding()
    return MockEmbedding()


# --- MatrixOne vecf32 format conversion ---


def embedding_to_vecf32(vec: list[float]) -> str:
    """Convert float vector to MatrixOne vecf32 string format: '[0.1,0.2,...]'."""
    return "[" + ",".join(str(f) for f in vec) + "]"


def vecf32_to_embedding(data: str | None) -> list[float] | None:
    """Parse MatrixOne vecf32 string back to list[float]."""
    if not data:
        return None
    return [float(x) for x in data.strip("[]").split(",")]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = np.dot(va, vb)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
