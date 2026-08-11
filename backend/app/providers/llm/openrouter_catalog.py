"""OpenRouter free-model catalog with in-process cache and round-robin cursor.

Free model availability changes often. We keep a curated seed list and optionally
refresh from the public OpenRouter models API (pricing prompt+completion == 0 or
id ending in ``:free``).
"""

from __future__ import annotations

import time
from typing import Any

# Curated seed — prefer general chat / instruction models. Refreshed live when possible.
SEED_FREE_MODELS: tuple[str, ...] = (
    "openrouter/free",
    "nvidia/nemotron-nano-9b-v2:free",
    "openai/gpt-oss-20b:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "inclusionai/ling-3.0-flash:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "poolside/laguna-xs-2.1:free",
    "poolside/laguna-s-2.1:free",
    "cohere/north-mini-code:free",
)

_cached_models: list[str] = list(SEED_FREE_MODELS)
_cached_at: float = 0.0
_CACHE_TTL_SECONDS = 3600.0
_cursor: int = 0


def get_cached_free_models() -> list[str]:
    return list(_cached_models) if _cached_models else list(SEED_FREE_MODELS)


def set_cached_free_models(models: list[str]) -> None:
    global _cached_models, _cached_at
    cleaned = [m.strip() for m in models if m and m.strip()]
    if cleaned:
        _cached_models = cleaned
        _cached_at = time.time()


def current_cursor() -> int:
    return _cursor


def advance_cursor(model: str | None = None) -> int:
    """Move the round-robin cursor past ``model`` (or +1)."""
    global _cursor
    models = get_cached_free_models()
    if not models:
        _cursor = 0
        return _cursor
    if model and model in models:
        _cursor = (models.index(model) + 1) % len(models)
    else:
        _cursor = (_cursor + 1) % len(models)
    return _cursor


def ordered_free_models(*, start: int | None = None) -> list[str]:
    """Return free models starting at the round-robin cursor (wrap once)."""
    models = get_cached_free_models()
    if not models:
        return []
    idx = current_cursor() if start is None else start % len(models)
    return models[idx:] + models[:idx]


def _is_free_model(entry: dict[str, Any]) -> bool:
    model_id = str(entry.get("id") or "")
    if model_id.endswith(":free") or model_id == "openrouter/free":
        return True
    pricing = entry.get("pricing") or {}
    try:
        prompt = float(pricing.get("prompt") or 0)
        completion = float(pricing.get("completion") or 0)
    except (TypeError, ValueError):
        return False
    return prompt == 0.0 and completion == 0.0 and bool(model_id)


async def refresh_free_models_from_api(
    *,
    api_key: str | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
    force: bool = False,
) -> list[str]:
    """Refresh cache from OpenRouter ``GET /models``. Falls back to seed on failure."""
    global _cached_at
    now = time.time()
    if not force and _cached_models and now - _cached_at < _CACHE_TTL_SECONDS:
        return get_cached_free_models()

    try:
        import httpx

        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            response.raise_for_status()
            payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return get_cached_free_models()
        free_ids = [str(row["id"]) for row in rows if isinstance(row, dict) and _is_free_model(row)]
        # Prefer chat-capable ids; keep openrouter/free first when present.
        free_ids = sorted(set(free_ids), key=lambda m: (0 if m == "openrouter/free" else 1, m))
        if free_ids:
            set_cached_free_models(free_ids)
    except Exception:
        if not _cached_models:
            set_cached_free_models(list(SEED_FREE_MODELS))
        _cached_at = now
    return get_cached_free_models()
