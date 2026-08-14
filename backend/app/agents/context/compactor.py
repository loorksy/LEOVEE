"""Fit the conversation into the budget without breaking it.

The order of operations is load-bearing:

1. **Drop stale market data outright.** It scores worst anyway, but removing it
   first means the expensive scoring pass never runs over the largest messages
   in the conversation.
2. **Truncate long prose**, marking where it was cut. A halved message that says
   nothing about being halved reads as a complete thought that trails off.
3. **Evict by score**, cheapest first, *taking each tool call and its result as
   one unit*. Evicting them independently is what orphans a result.
4. **Repair** anything still unpaired, and hard-fail if the important messages
   alone exceed the budget — a silently over-budget context is a provider error
   at send time, thrown from a layer that has no idea why.

Nothing important is ever evicted. The constitution and the current user message
are the run; a compactor that can drop them under pressure produces an
unguided model at exactly the moment the conversation got complicated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.context.budget import estimate_context_tokens
from app.agents.context.messages import ContextMessage, MessageKind
from app.agents.context.relevance import score_message

__all__ = ["CompactionResult", "compact_conversation", "ContextOverflowError"]

#: Turns at the tail that are treated as recent and given a scoring bonus. The
#: last few exchanges carry the thread of the conversation regardless of how
#: they score on term overlap.
DEFAULT_RECENT_RESERVE = 8
RECENT_BONUS = 20

#: Prose longer than this is truncated rather than evicted: half a memory is
#: worth more than none, unlike half a tool result.
PROSE_LIMIT = 1_200
TOOL_RESULT_LIMIT = 600
TRUNCATION_MARK = " …[اختُصر]"


class ContextOverflowError(RuntimeError):
    """The pinned messages alone do not fit.

    Raised rather than sending anyway: an over-budget request fails at the
    provider with an opaque error, several layers from the cause, and after the
    tokens have been spent.
    """


@dataclass(slots=True)
class CompactionResult:
    messages: list[ContextMessage]
    estimated_tokens: int
    removed_ids: list[str] = field(default_factory=list)
    truncated_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def compacted(self) -> bool:
        return bool(self.removed_ids or self.truncated_ids)


def _truncate(message: ContextMessage) -> bool:
    limit = TOOL_RESULT_LIMIT if message.kind is MessageKind.TOOL_RESULT else PROSE_LIMIT
    if len(message.content) <= limit:
        return False
    message.content = message.content[:limit].rstrip() + TRUNCATION_MARK
    return True


def _pair_id(message: ContextMessage) -> str | None:
    if message.kind in (MessageKind.TOOL_CALL, MessageKind.TOOL_RESULT):
        return message.tool_call_id
    return None


def compact_conversation(
    messages: list[ContextMessage],
    *,
    token_budget: int,
    query: str = "",
    symbol: str | None = None,
    timeframe: str | None = None,
    recommendation_id: str | None = None,
    analysis_id: str | None = None,
    recent_reserve: int = DEFAULT_RECENT_RESERVE,
) -> CompactionResult:
    budget = max(0, token_budget)
    removed: list[str] = []
    truncated: list[str] = []
    warnings: list[str] = []

    kept: list[ContextMessage] = []
    for message in messages:
        if message.historical_market_data and not message.important:
            removed.append(message.id)
            warnings.append(f"historical_market_data_omitted:{message.id}")
            continue
        if _truncate(message):
            truncated.append(message.id)
        kept.append(message)

    recent_ids = {m.id for m in kept[-max(2, recent_reserve) :]}

    def rank(message: ContextMessage) -> tuple[int, int]:
        score = score_message(
            message,
            query=query,
            symbol=symbol,
            timeframe=timeframe,
            recommendation_id=recommendation_id,
            analysis_id=analysis_id,
        )
        if message.id in recent_ids:
            score += RECENT_BONUS
        if message.kind in (MessageKind.TOOL_CALL, MessageKind.TOOL_RESULT):
            score += 2
        return score, message.sequence

    while estimate_context_tokens(kept) > budget:
        candidates = sorted((m for m in kept if not m.important), key=rank)
        if not candidates:
            break
        victim = candidates[0]
        pair = _pair_id(victim)
        # The call and its result leave together. Evicting one alone is the
        # orphan the repair pass then has to invent a result for.
        doomed = {victim.id} | ({m.id for m in kept if _pair_id(m) == pair} if pair else set())
        kept = [m for m in kept if m.id not in doomed or m.important]
        removed.extend(sorted(doomed))

    kept, repair_warnings = _repair_pairs(kept)
    warnings.extend(repair_warnings)

    total = estimate_context_tokens(kept)
    if total > budget:
        raise ContextOverflowError(
            f"pinned messages need {total} tokens but the budget is {budget}; "
            "reduce the system prompt or raise the budget rather than sending"
        )

    return CompactionResult(
        messages=kept,
        estimated_tokens=total,
        removed_ids=removed,
        truncated_ids=truncated,
        warnings=warnings,
    )


def _repair_pairs(messages: list[ContextMessage]) -> tuple[list[ContextMessage], list[str]]:
    """Drop any tool call or result left without its counterpart."""
    calls = {m.tool_call_id for m in messages if m.kind is MessageKind.TOOL_CALL}
    results = {m.tool_call_id for m in messages if m.kind is MessageKind.TOOL_RESULT}
    complete = calls & results
    warnings: list[str] = []
    kept: list[ContextMessage] = []
    for message in messages:
        pair = _pair_id(message)
        if pair is not None and pair not in complete:
            warnings.append(f"unpaired_tool_message_removed:{message.id}")
            continue
        kept.append(message)
    return kept, warnings
