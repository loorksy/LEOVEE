"""How much this turn needs a given message.

The weights are a ranking, not a measurement — their only job is to order
messages so the least useful goes first. Two of them carry most of the value:

**An exact recommendation or analysis id outranks everything else.** A question
about a specific recommendation needs *that* recommendation's turn, and term
overlap will not find it: the user says "the gold one from this morning" and the
turn says a UUID.

**Stale market data scores negative, not zero.** Old candles are not merely
unhelpful, they are wrong — the live numbers are already in this turn's
evidence, and a model reading both has to reconcile two contradictory pictures
of the same market. Being first to go is the point.
"""

from __future__ import annotations

import re

from app.agents.context.messages import ContextMessage, MessageKind

__all__ = ["context_terms", "score_message", "IMPORTANT_SCORE"]

_TERM = re.compile(r"[^\W_]{2,}", re.UNICODE)

#: Above any accumulation of ordinary signals: important messages are pinned.
IMPORTANT_SCORE = 100

_PREFERENCE = re.compile(r"(preference|risk|أفضل|افضل|تفضيل|مخاطر)", re.IGNORECASE | re.UNICODE)


def context_terms(value: str) -> set[str]:
    return {match.group(0).lower() for match in _TERM.finditer(value)}


def score_message(
    message: ContextMessage,
    *,
    query: str,
    symbol: str | None = None,
    timeframe: str | None = None,
    recommendation_id: str | None = None,
    analysis_id: str | None = None,
) -> int:
    score = IMPORTANT_SCORE if message.important else 0

    haystack = context_terms(
        " ".join(
            part
            for part in (
                message.content,
                message.symbol,
                message.timeframe,
                message.recommendation_id,
                message.analysis_id,
            )
            if part
        )
    )
    score += 3 * len(context_terms(query) & haystack)

    if symbol and message.symbol == symbol.upper():
        score += 8
    if timeframe and message.timeframe == timeframe.upper():
        score += 5
    if recommendation_id and message.recommendation_id == recommendation_id:
        score += 12
    if analysis_id and message.analysis_id == analysis_id:
        score += 12

    if message.kind is MessageKind.RECOMMENDATION:
        score += 4
    if message.kind is MessageKind.MEMORY and _PREFERENCE.search(message.content):
        score += 6
    if message.historical_market_data:
        score -= 20
    return score
