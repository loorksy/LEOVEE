"""Embeddings: real vectors, and a fallback that never lies about itself."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError
from app.providers.llm.embeddings import (
    DETERMINISTIC_MODEL,
    EMBEDDING_DIM,
    EmbeddingResult,
    cosine_similarity,
    get_embedding_provider,
)
from app.services.memory.embedding import embed_text_deterministic

pytestmark = pytest.mark.no_db


def test_hashed_vectors_carry_no_semantic_similarity() -> None:
    """The reason this layer needed replacing, pinned as a test.

    Hashing is *designed* so that similar inputs land far apart. Two paraphrases
    of one observation get orthogonal vectors, so nearest-neighbour search over
    them ranks by nothing and returns whichever rows the index happened to
    visit — while looking exactly like a working retrieval.
    """
    related = cosine_similarity(
        embed_text_deterministic("gold broke resistance on strong volume"),
        embed_text_deterministic("XAUUSD broke through resistance with volume"),
    )
    unrelated = cosine_similarity(
        embed_text_deterministic("gold broke resistance on strong volume"),
        embed_text_deterministic("the harbour ferry runs every twenty minutes"),
    )
    # Neither is meaningfully larger — that is the whole point.
    assert abs(related - unrelated) < 0.2


def test_the_deterministic_vectors_are_still_stable_and_correctly_shaped() -> None:
    """They remain a valid test double; they were only ever wrong as a default."""
    a = embed_text_deterministic("hello")
    assert a == embed_text_deterministic("hello")
    assert len(a) == EMBEDDING_DIM


def test_no_provider_configured_raises_rather_than_falling_back_silently() -> None:
    """An offline index that looks like a real one is the failure to avoid."""
    settings = Settings(OPENAI_API_KEY=None, ANTHROPIC_API_KEY=None, OPENROUTER_API_KEY=None)
    with pytest.raises(ProviderConfigurationError, match="test double"):
        get_embedding_provider(settings)


def test_the_deterministic_tag_is_never_a_real_model_name() -> None:
    assert DETERMINISTIC_MODEL == "deterministic-v1"
    assert "embedding" not in DETERMINISTIC_MODEL


def test_an_empty_result_refuses_to_produce_a_vector() -> None:
    from app.providers.llm.errors import LLMError

    with pytest.raises(LLMError, match="no vectors"):
        _ = EmbeddingResult(vectors=[], model="m").one


def test_cosine_similarity_handles_the_degenerate_cases() -> None:
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
