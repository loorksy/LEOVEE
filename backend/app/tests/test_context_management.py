"""Context management: fit the window without losing the thread."""

from __future__ import annotations

import pytest

from app.agents.context import (
    ContextMessage,
    MessageKind,
    compact_conversation,
    estimate_context_tokens,
    estimate_text_tokens,
    score_message,
)
from app.agents.context.compactor import ContextOverflowError

pytestmark = pytest.mark.no_db


def _msg(
    seq: int,
    content: str = "some conversation text",
    kind: MessageKind = MessageKind.USER,
    **kwargs: object,
) -> ContextMessage:
    return ContextMessage(id=f"m{seq}", kind=kind, content=content, sequence=seq, **kwargs)  # type: ignore[arg-type]


# --- estimation --------------------------------------------------------------


def test_an_empty_string_costs_nothing_and_any_text_costs_something() -> None:
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("a") == 1


def test_tool_arguments_are_charged_too() -> None:
    """They travel to the provider like anything else; not counting them is how
    an estimate passes and the request is rejected."""
    plain = _msg(1, "hello")
    with_args = _msg(2, "hello", kind=MessageKind.TOOL_CALL, tool_arguments="x" * 400)
    assert estimate_context_tokens([with_args]) > estimate_context_tokens([plain])


# --- relevance ---------------------------------------------------------------


def test_stale_market_data_scores_below_zero_not_merely_low() -> None:
    """Old candles are wrong, not just unhelpful — the live ones are in evidence."""
    stale = _msg(1, "candles: 2000, 2001, 2002", historical_market_data=True)
    assert score_message(stale, query="gold") < 0


def test_an_exact_recommendation_id_outranks_term_overlap() -> None:
    """The user says "the gold one from this morning"; the turn holds a UUID."""
    by_id = _msg(1, "unrelated wording entirely", recommendation_id="rec-1")
    by_words = _msg(2, "gold gold gold analysis")
    query = "gold analysis"
    assert score_message(by_id, query=query, recommendation_id="rec-1") > score_message(
        by_words, query=query, recommendation_id="rec-1"
    )


def test_an_important_message_outranks_any_accumulation_of_signals() -> None:
    pinned = _msg(1, "constitution", important=True)
    loaded = _msg(2, "gold XAUUSD M15 analysis", symbol="XAUUSD", timeframe="M15")
    assert score_message(pinned, query="") > score_message(
        loaded, query="gold XAUUSD M15 analysis", symbol="XAUUSD", timeframe="M15"
    )


# --- compaction --------------------------------------------------------------


def test_a_conversation_within_budget_is_returned_untouched() -> None:
    messages = [_msg(i) for i in range(5)]
    result = compact_conversation(messages, token_budget=10_000)
    assert result.compacted is False
    assert len(result.messages) == 5


def test_stale_market_data_goes_first_and_says_so() -> None:
    messages = [
        _msg(0, "x" * 100, historical_market_data=True),
        _msg(1, "the actual question", important=True),
    ]
    result = compact_conversation(messages, token_budget=10_000)
    assert [m.id for m in result.messages] == ["m1"]
    assert any(w.startswith("historical_market_data_omitted") for w in result.warnings)


def test_important_messages_are_never_evicted() -> None:
    """A compactor that can drop the constitution produces an unguided model at
    exactly the moment the conversation got complicated."""
    messages = [_msg(0, "system rules", important=True)] + [
        _msg(i, "x" * 800) for i in range(1, 12)
    ]
    result = compact_conversation(messages, token_budget=600)
    assert "m0" in {m.id for m in result.messages}


def test_a_tool_call_and_its_result_are_evicted_together() -> None:
    """Evicting one alone is precisely what orphans the other."""
    messages = [
        _msg(0, "current question", important=True),
        _msg(1, "x" * 3_000, kind=MessageKind.TOOL_CALL, tool_call_id="t1"),
        _msg(2, "y" * 300, kind=MessageKind.TOOL_RESULT, tool_call_id="t1"),
    ]
    result = compact_conversation(messages, token_budget=200)
    ids = {m.id for m in result.messages}
    assert "m1" not in ids and "m2" not in ids


def test_an_orphan_that_survives_eviction_is_repaired_away() -> None:
    """A result whose call was never in the conversation is malformed history,
    and providers reject it as an opaque request error far from the cause."""
    messages = [
        _msg(0, "question", important=True),
        _msg(1, "result with no call", kind=MessageKind.TOOL_RESULT, tool_call_id="ghost"),
    ]
    result = compact_conversation(messages, token_budget=10_000)
    assert [m.id for m in result.messages] == ["m0"]
    assert any(w.startswith("unpaired_tool_message_removed") for w in result.warnings)


def test_long_prose_is_truncated_visibly_rather_than_silently() -> None:
    """A halved message that does not say so reads as a thought that trails off."""
    messages = [_msg(0, "و" * 5_000, kind=MessageKind.MEMORY)]
    result = compact_conversation(messages, token_budget=10_000)
    assert result.truncated_ids == ["m0"]
    assert result.messages[0].content.endswith("…[اختُصر]")


def test_tool_results_are_truncated_harder_than_prose() -> None:
    prose = _msg(0, "و" * 5_000, kind=MessageKind.MEMORY)
    tool = _msg(1, "و" * 5_000, kind=MessageKind.TOOL_RESULT, tool_call_id="t")
    compact_conversation([prose], token_budget=10_000)
    compact_conversation([tool], token_budget=10_000)
    assert len(tool.content) < len(prose.content)


def test_a_context_that_cannot_fit_fails_loudly_rather_than_being_sent() -> None:
    """Sending it anyway costs the tokens and returns an opaque provider error."""
    messages = [_msg(i, "x" * 4_000, important=True) for i in range(5)]
    with pytest.raises(ContextOverflowError, match="rather than sending"):
        compact_conversation(messages, token_budget=100)


def test_compaction_is_deterministic() -> None:
    """Ties break on sequence, so the same input always drops the same turns."""

    def build() -> list[ContextMessage]:
        return [_msg(0, "q", important=True)] + [_msg(i, "x" * 500) for i in range(1, 15)]

    first = compact_conversation(build(), token_budget=900)
    for _ in range(5):
        assert compact_conversation(build(), token_budget=900).removed_ids == first.removed_ids
