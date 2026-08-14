"""Which timeframes this platform works on, and who chooses.

Leovee trades **scalp only** (owner decision). Two rules follow, and they are
different rules that are easy to conflate:

**The decision timeframe is M1, M5 or M15.** That is the range a scalp lives in;
anything slower is a different trade with a different holding period, risk
profile and invalidation.

**The agent chooses it, not the user.** There is no timeframe selector. Which
frame carries the setup is an analytical judgement — it depends on where
structure is legible and where the move is actually forming — and exposing it as
a control invites the user to ask for a 1-minute answer on a chart that has
nothing to say at 1 minute. This mirrors AiChart's constitution, which the
decision doctrine already follows (ADR 0002): *the trading style follows the
analysed timeframe; it is never a user-selectable mode.*

Higher frames stay, as **context only**. The same constitution says higher
timeframes give context, and that when frames conflict the answer must name
which one leads the decision, which gives context, and which times the entry. A
scalp read with no idea where H1 sits is how a trader ends up selling into a
strong uptrend on a 3-minute pullback.

Excluded deliberately: **M30**, which sits between M15 and H1 and tells a scalper
nothing either of its neighbours does not; and **D1**, too coarse to time a
one-minute entry, with its longer-horizon bias already carried by H4.
"""

from __future__ import annotations

from app.models.enums import Timeframe

__all__ = [
    "DECISION_TIMEFRAMES",
    "CONTEXT_TIMEFRAMES",
    "ACTIVE_TIMEFRAMES",
    "MTF_CONTEXT_STACK",
    "MTF_CONTEXT_STACK_CODES",
    "DEFAULT_SERIES_TIMEFRAME",
    "MIN_CANDLES_FOR_ANALYSIS",
    "ANALYSIS_WINDOW_BARS",
    "is_decision_timeframe",
    "is_active_timeframe",
]

#: The agent picks one of these per analysis. Ordered fastest to slowest.
DECISION_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M15,
)

#: Read for bias and structure. Never the frame a scalp is executed on.
CONTEXT_TIMEFRAMES: tuple[Timeframe, ...] = (Timeframe.H1, Timeframe.H4)

#: Everything the platform fetches, stores and keeps warm.
ACTIVE_TIMEFRAMES: tuple[Timeframe, ...] = DECISION_TIMEFRAMES + CONTEXT_TIMEFRAMES

#: Slowest first: the multi-timeframe engine walks from context down to the
#: fastest frame that still carries structure. The stock stack was D1/H4/H1,
#: which is a swing trader's ladder — for a scalp, M15 is part of the context,
#: not an afterthought below it.
MTF_CONTEXT_STACK: tuple[Timeframe, ...] = (Timeframe.H4, Timeframe.H1, Timeframe.M15)

#: The same stack as plain strings, for engines keyed on timeframe codes.
MTF_CONTEXT_STACK_CODES: tuple[str, ...] = tuple(tf.value for tf in MTF_CONTEXT_STACK)

#: The frame to assume when nothing says which one this is.
#:
#: It began life as ``INTERIM_DECISION_TIMEFRAME``, a stand-in until the agent's
#: real selection logic landed. That logic has landed
#: (``app/agents/timeframe.py``), so the name is now wrong in the way the engine
#: ledger exists to prevent: a symbol that describes itself as temporary
#: scaffolding, long after the thing it was scaffolding was built, is a comment
#: that has quietly become false.
#:
#: What remains is a narrower and permanent job. Three places have a single
#: candle series and no record of its frame — an engine called with one series,
#: a stored plan whose ``timeframe`` column is null or unparseable, an MTF read
#: with nothing to compare. Each needs *a* frame to label the series with, and
#: the top of the scalping range is the most stable choice. **It is never a
#: decision**: where a frame is actually chosen, ``select_decision_timeframe``
#: chooses it, and a run that cannot choose fails closed with
#: ``NO_VIABLE_TIMEFRAME`` rather than reaching for this.
DEFAULT_SERIES_TIMEFRAME: Timeframe = Timeframe.M15

#: Below this, the deterministic engines have nothing to work with. The bound
#: comes from AiChart's detectGeometry, which needs enough bars to confirm
#: pivots before it will call a structure.
MIN_CANDLES_FOR_ANALYSIS = 60

#: The window the geometry engine reads. Also from detectGeometry: bounded
#: output is what keeps a chart snapshot usable as model context, and an
#: unbounded window blows up both the token budget and the drawing density.
ANALYSIS_WINDOW_BARS = 500


def is_decision_timeframe(timeframe: Timeframe | str) -> bool:
    """May a recommendation be made on this frame?"""
    return Timeframe(timeframe) in DECISION_TIMEFRAMES


def is_active_timeframe(timeframe: Timeframe | str) -> bool:
    """Does the platform fetch and store this frame at all?"""
    return Timeframe(timeframe) in ACTIVE_TIMEFRAMES
