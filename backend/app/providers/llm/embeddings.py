"""Real embeddings, with a labelled offline fallback.

The memory layer indexed on ``embed_text_deterministic`` — a SHA-256 hash spread
across 1536 dimensions. It is stable and needs no network, which is why it was a
reasonable stand-in, but it is **not an embedding**: hashing is designed so that
similar inputs land far apart. Two paraphrases of the same market observation
get orthogonal vectors, so a nearest-neighbour search over them ranks by nothing
at all and quietly returns whichever rows the index visited first.

That matters most where it is least visible. The learning loop retrieves
"similar past cases" to calibrate confidence; if retrieval is random, the
calibration measures noise and reports it as experience.

**Every vector carries the model that produced it, and searches filter on it.**
Cosine distance between a real embedding and a hashed one is meaningless, and a
single HNSW index holding both silently mixes them. The label is the only thing
that keeps two generations of vectors apart, so it is required rather than
defaulted — a row tagged ``text-embedding-3-small`` that a hash produced is a
lie the schema itself tells.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ProviderConfigurationError
from app.providers.llm.errors import LLMError

__all__ = [
    "EMBEDDING_DIM",
    "DETERMINISTIC_MODEL",
    "EmbeddingResult",
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "get_embedding_provider",
    "cosine_similarity",
]

EMBEDDING_DIM = 1536

#: The tag every hashed vector carries. Never a real model name.
DETERMINISTIC_MODEL = "deterministic-v1"

_DEFAULT_MODEL = "text-embedding-3-small"


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str

    @property
    def one(self) -> list[float]:
        if not self.vectors:
            raise LLMError("embedding provider returned no vectors", code="embedding_empty")
        return self.vectors[0]


class EmbeddingProvider(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


class OpenAIEmbeddingProvider:
    """OpenAI embeddings. The only real provider wired today."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self.model)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model, "input": texts},
            )
            if response.status_code >= 400:
                raise LLMError(
                    f"embedding request failed: {response.status_code} {response.text[:200]}",
                    code="embedding_http_error",
                    retryable=response.status_code >= 500 or response.status_code == 429,
                )
            payload: dict[str, Any] = response.json()
        # Sorted by index: the API does not promise input order, and a silent
        # reordering would attach every vector to the wrong memory.
        items = sorted(payload.get("data", []), key=lambda item: int(item.get("index", 0)))
        vectors = [[float(v) for v in item["embedding"]] for item in items]
        for vector in vectors:
            if len(vector) != EMBEDDING_DIM:
                raise LLMError(
                    f"embedding dimension mismatch: got {len(vector)}, "
                    f"column is Vector({EMBEDDING_DIM})",
                    code="embedding_dimension_mismatch",
                    retryable=False,
                )
        return EmbeddingResult(vectors=vectors, model=payload.get("model", self.model))


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """The configured provider, or a configuration error.

    No silent fall back to the hashed vectors: an offline index that looks like
    a real one is exactly the failure this module exists to end. Callers that
    genuinely want the deterministic stand-in ask for it by name, in tests.
    """
    resolved = settings or get_settings()
    if resolved.openai_api_key:
        return OpenAIEmbeddingProvider(resolved.openai_api_key)
    raise ProviderConfigurationError(
        "No embedding provider configured (OPENAI_API_KEY). Memory indexing "
        "requires real embeddings; the deterministic vectors are a test double."
    )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
