"""The one place that answers "is the gold market open right now".

Ported from AiChart's ``src/lib/markets/tradingCalendar.ts``, whose comments
record two bugs worth not reintroducing:

**The week is New York wall time, not a fixed UTC hour.** The week opens Sunday
evening and closes Friday 17:00 America/New_York. Hard-coding 22:00 UTC is
correct only in winter — 17:00 NY is 21:00 UTC under EDT — so for half the year
a phantom "missing" daily bar appeared every week and blocked analysis on a
perfectly healthy series.

**Gold halts daily.** The feed stops for [17:00, 18:00) New York each weekday.
Treating gold like a currency pair produced four phantom missing 15m bars per
day, and gold analysis was permanently reported as gapped. Since Leovee trades
gold and nothing else (ADR 0007), this is not an edge case here — it is the
session model.

Exchange holidays are deliberately *not* modelled, matching AiChart. A missed
holiday shows up as a small gap that the ratio-based gap policy tolerates;
modelling holidays means maintaining a calendar per venue per year, and getting
that subtly wrong blocks analysis rather than degrading it.

DST comes from ``zoneinfo`` rather than fixed offsets — the specification (§3)
requires IANA definitions with correct DST handling, tested across transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.core.symbols import AssetGroup, instrument_for

__all__ = [
    "TradingClass",
    "SessionStatus",
    "resolve_trading_class",
    "is_market_open_at",
    "is_expected_daily_bar_open",
    "get_session_status",
]

NY = ZoneInfo("America/New_York")

#: Week close, New York wall-clock hour. Shared by gold and the FX fallback.
WEEK_CLOSE_HOUR_NY = 17
#: Gold reopens Sunday 18:00 NY, an hour after the FX week.
METAL_SUNDAY_OPEN_HOUR_NY = 18
#: Gold halts [17:00, 18:00) NY each weekday (CME maintenance).
METAL_BREAK_HOUR_NY = 17
#: FX week open, used only by the conservative fallback below.
FX_WEEK_OPEN_HOUR_NY = 17


class TradingClass(StrEnum):
    METAL = "metal"
    #: Anything not on the allowlist. Reachable only if a symbol slips past the
    #: gate, so it is deliberately the conservative shape — closed at weekends
    #: rather than assumed always open.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SessionStatus:
    is_open: bool
    #: A stable machine-readable cause. User-facing wording lives in the
    #: frontend dictionary so it can be translated (Arabic is the default
    #: locale), rather than being baked into the backend in one language.
    reason: str


def resolve_trading_class(symbol: str) -> TradingClass:
    spec = instrument_for(symbol)
    if spec is None:
        return TradingClass.UNKNOWN
    return TradingClass.METAL if spec.group is AssetGroup.METAL else TradingClass.UNKNOWN


def _ny_weekday_hour(moment: datetime) -> tuple[int, int]:
    """New York weekday (Sunday = 0) and hour for an instant."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = moment.astimezone(NY)
    # Python's weekday() is Monday = 0; the session rules are written around
    # Sunday = 0, matching the reference implementation.
    return (local.weekday() + 1) % 7, local.hour


def is_market_open_at(symbol: str, moment: datetime) -> bool:
    """
    gold:    Sun 18:00 NY → Fri 17:00 NY, halted [17:00, 18:00) NY Mon–Thu
    unknown: Sun 17:00 NY → Fri 17:00 NY (conservative fallback)
    """
    trading_class = resolve_trading_class(symbol)
    weekday, hour = _ny_weekday_hour(moment)

    if weekday == 6:  # Saturday
        return False
    if weekday == 5 and hour >= WEEK_CLOSE_HOUR_NY:  # Friday close
        return False

    if trading_class is TradingClass.METAL:
        if weekday == 0 and hour < METAL_SUNDAY_OPEN_HOUR_NY:
            return False
        # Friday >= 17:00 already returned above, so this is Mon–Thu.
        return hour != METAL_BREAK_HOUR_NY

    return not (weekday == 0 and hour < FX_WEEK_OPEN_HOUR_NY)


def is_expected_daily_bar_open(symbol: str, open_at: datetime) -> bool:
    """Should a daily bar exist with this open timestamp?

    Daily candles align to 17:00 New York regardless of DST, giving five bars in
    a normal week (Sunday–Thursday opens covering the Monday–Friday sessions).
    Stepping "previous open + 24h" cannot express that: the step drifts an hour
    across each DST transition, and a fixed-UTC check then declares a phantom
    weekly gap.
    """
    weekday, hour = _ny_weekday_hour(open_at)
    return hour == WEEK_CLOSE_HOUR_NY and 0 <= weekday <= 4


def get_session_status(symbol: str, now: datetime | None = None) -> SessionStatus:
    moment = now or datetime.now(UTC)
    if is_market_open_at(symbol, moment):
        return SessionStatus(is_open=True, reason="MARKET_OPEN")

    weekday, hour = _ny_weekday_hour(moment)
    if weekday == 6:
        return SessionStatus(is_open=False, reason="WEEKEND")
    if weekday == 5 and hour >= WEEK_CLOSE_HOUR_NY:
        return SessionStatus(is_open=False, reason="WEEK_CLOSED")
    if weekday == 0:
        return SessionStatus(is_open=False, reason="WEEK_NOT_OPEN_YET")
    return SessionStatus(is_open=False, reason="DAILY_MAINTENANCE_BREAK")
