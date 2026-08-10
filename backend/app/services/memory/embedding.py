from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable

EMBEDDING_DIM = 1536


def embed_text_deterministic(text: str, *, dim: int = EMBEDDING_DIM) -> list[float]:
    """Local deterministic embedding for tests and offline indexing (Phase 20)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dim:
        for i in range(0, len(digest), 4):
            chunk = digest[i : i + 4]
            if len(chunk) < 4:
                break
            n = int.from_bytes(chunk, "big") / 2**32
            values.append(n * 2 - 1)
            if len(values) >= dim:
                break
        digest = hashlib.sha256(digest).digest()
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def merge_rank_hybrid(
    keyword_hits: list[dict[str, object]],
    vector_hits: list[dict[str, object]],
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    """Simple hybrid merge: vector first, then keyword backfill."""
    seen: set[str] = set()
    merged: list[dict[str, object]] = []
    for item in vector_hits + keyword_hits:
        key = str(item.get("id", ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def batch_embed(texts: Iterable[str]) -> list[list[float]]:
    return [embed_text_deterministic(t) for t in texts]
