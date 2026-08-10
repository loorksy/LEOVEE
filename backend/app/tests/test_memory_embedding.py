from __future__ import annotations

from app.services.memory.embedding import EMBEDDING_DIM, embed_text_deterministic, merge_rank_hybrid


def test_embed_text_is_deterministic_normalized() -> None:
    a = embed_text_deterministic("hello")
    b = embed_text_deterministic("hello")
    assert a == b
    assert len(a) == EMBEDDING_DIM


def test_hybrid_merge_dedupes() -> None:
    merged = merge_rank_hybrid(
        [{"id": "1", "key": "a"}],
        [{"id": "1", "key": "a"}, {"id": "2", "key": "b"}],
        limit=5,
    )
    assert len(merged) == 2
