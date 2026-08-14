"""The evidence gate: what must be read before a direction is published.

A recommendation is a claim, and the platform's whole posture is that it does
not make a claim it did not check. This gate turns "the agent should read the
news, the liquidity map, the session, the live price before deciding" from a
hope written in a prompt into a **deterministic precondition**: the directional
decision stage is not reached unless every mandatory reading is present and
fresh, and the reasons are named when it is not.

Two tiers, and the difference is deliberate:

- **Blocking** — the recommendation cannot be published. The market is closed;
  a high-impact economic event is imminent (you do not scalp gold ninety
  seconds before CPI); the price the analysis read is stale. Each fails the run
  closed with a named reason, exactly like a missing engine.
- **Advisory** — surfaced to the decision and to the reader, never hidden, but
  not a veto: thin liquidity, a quiet or violent regime, news the provider
  could not refresh. Gold trades through all of these; the reader is told, and
  the model weighs it.

Everything here is gold-specific by construction — the sessions are the metal's
sessions, the freshness windows are scalp windows, the event blackout is the
one that actually moves the metal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from app.models.enums import Timeframe

CheckStatus = Literal["ok", "warning", "stale", "absent"]

__all__ = [
    "EVENT_BLACKOUT_BEFORE",
    "EVENT_BLACKOUT_AFTER",
    "EconomicEvent",
    "NewsContext",
    "EvidenceCheck",
    "EvidenceReport",
    "assess_evidence",
]

#: How close to a high-impact event a scalp is refused, and how long after it
#: the blackout persists. A one-minute plan written into the CPI print is not a
#: read of the market; it is a coin flip on the release.
EVENT_BLACKOUT_BEFORE = timedelta(minutes=15)
EVENT_BLACKOUT_AFTER = timedelta(minutes=5)

#: A decision is stale when the newest candle is older than this multiple of the
#: decision frame. Three bars: past that, the price the plan is written at is not
#: the price on the screen.
_STALENESS_BARS = 3
_FRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
}


@dataclass(frozen=True, slots=True)
class EconomicEvent:
    """A scheduled release that moves gold — NFP, CPI, FOMC, and the like."""

    ts: datetime
    title: str
    impact: Literal["high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class NewsContext:
    """What the news read returned. Absence of a provider is a fact, not a gap."""

    provider_configured: bool
    headline_count: int
    latest_headline_ts: datetime | None
    upcoming_events: tuple[EconomicEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    name: str
    status: CheckStatus
    #: True when a failing status blocks publication rather than merely warning.
    blocking: bool
    detail: str
    value: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status in ("stale", "absent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "blocking": self.blocking,
            "detail": self.detail,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    checks: tuple[EvidenceCheck, ...]

    @property
    def block_reason(self) -> str | None:
        for check in self.checks:
            if check.blocking and check.failed:
                return f"EVIDENCE_{check.name.upper()}"
        return None

    @property
    def blocked(self) -> bool:
        return self.block_reason is not None

    @property
    def warnings(self) -> list[str]:
        return [c.name for c in self.checks if not c.blocking and c.status in ("warning", "stale")]

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "warnings": self.warnings,
            "checks": [c.to_dict() for c in self.checks],
        }


def _bool_check(name: str, present: bool, detail_present: str, detail_absent: str) -> EvidenceCheck:
    return EvidenceCheck(
        name=name,
        status="ok" if present else "absent",
        blocking=True,
        detail=detail_present if present else detail_absent,
    )


def _session_check(session_status: dict[str, Any]) -> EvidenceCheck:
    """The metal's active session, and whether it is open at all."""
    is_open = bool(session_status.get("is_open", session_status.get("open", False)))
    session = str(session_status.get("session") or session_status.get("name") or "unknown")
    return EvidenceCheck(
        name="trading_session",
        status="ok" if is_open else "absent",
        blocking=True,
        detail=(f"{session} session, market open" if is_open else "market closed"),
        value={"session": session, "is_open": is_open},
    )


def _news_check(news: NewsContext, now: datetime) -> EvidenceCheck:
    """News was *read*. Advisory: gold trades without a fresh headline, but the
    reader is always told what the read found."""
    if not news.provider_configured:
        return EvidenceCheck(
            name="market_intelligence",
            status="warning",
            blocking=False,
            detail="news provider not configured; analysis proceeds without a headline read",
            value={"provider_configured": False},
        )
    if news.headline_count == 0:
        return EvidenceCheck(
            name="market_intelligence",
            status="warning",
            blocking=False,
            detail="no recent headlines returned",
            value={"provider_configured": True, "headline_count": 0},
        )
    age_min = (
        (now - news.latest_headline_ts).total_seconds() / 60
        if news.latest_headline_ts is not None
        else None
    )
    stale = age_min is not None and age_min > 180
    return EvidenceCheck(
        name="market_intelligence",
        status="stale" if stale else "ok",
        blocking=False,
        detail=(
            f"{news.headline_count} headlines, newest {round(age_min)}m ago"
            if age_min is not None
            else f"{news.headline_count} headlines"
        ),
        value={"provider_configured": True, "headline_count": news.headline_count},
    )


def _event_blackout_check(events: tuple[EconomicEvent, ...], now: datetime) -> EvidenceCheck:
    """No high-impact release inside the blackout window."""
    for event in events:
        if event.impact != "high":
            continue
        if now - EVENT_BLACKOUT_AFTER <= event.ts <= now + EVENT_BLACKOUT_BEFORE:
            minutes = round((event.ts - now).total_seconds() / 60)
            detail = f"high-impact event in the blackout window: {event.title} ({minutes:+d}m)"
            return EvidenceCheck(
                name="event_blackout",
                status="absent",
                blocking=True,
                detail=detail,
                value={"title": event.title, "minutes": minutes},
            )
    return EvidenceCheck(
        name="event_blackout",
        status="ok",
        blocking=True,
        detail="no high-impact event inside the blackout window",
    )


def _live_price_check(
    last_bar_ts: datetime, now: datetime, decision_timeframe: Timeframe
) -> EvidenceCheck:
    """The final verification against the live price: is the analysed candle
    recent enough that the plan is written at the price on the screen?"""
    frame_min = _FRAME_MINUTES.get(decision_timeframe, 15)
    age_min = (now - last_bar_ts).total_seconds() / 60
    limit = frame_min * _STALENESS_BARS
    stale = age_min > limit
    return EvidenceCheck(
        name="live_price",
        status="stale" if stale else "ok",
        blocking=True,
        detail=(
            f"newest candle {round(age_min)}m old (> {limit}m limit)"
            if stale
            else f"newest candle {round(age_min)}m old, within {limit}m"
        ),
        value={"age_minutes": round(age_min, 1), "limit_minutes": limit},
    )


def _regime_check(volatility: dict[str, Any]) -> EvidenceCheck:
    regime = str(volatility.get("regime") or "unknown")
    quiet_or_wild = regime in ("dead", "flat", "berserk", "volatile")
    return EvidenceCheck(
        name="volatility_regime",
        status="warning" if quiet_or_wild else "ok",
        blocking=False,
        detail=f"{regime} regime",
        value={"regime": regime},
    )


def assess_evidence(
    *,
    engines: dict[str, Any],
    session_status: dict[str, Any],
    news: NewsContext,
    last_bar_ts: datetime,
    now: datetime,
    decision_timeframe: Timeframe,
) -> EvidenceReport:
    """Assemble the mandatory pre-decision reading for gold.

    Order matters for the reader, not the logic: structure and liquidity first
    (what the market is doing), then the session and news (the context it does
    it in), then the two hard gates — the event blackout and the live-price
    freshness — that decide whether a scalp may be written at all right now.
    """
    liquidity = engines.get("liquidity") or {}
    structure = engines.get("structure") or {}
    checks: list[EvidenceCheck] = [
        _bool_check(
            "market_structure",
            bool(structure),
            "structure read (swings, BOS/CHoCH)",
            "no structure read",
        ),
        _bool_check(
            "liquidity_map",
            bool(liquidity),
            "liquidity read (sweeps, pools, equal highs/lows)",
            "no liquidity read",
        ),
        _bool_check(
            "supply_demand",
            bool(engines.get("zones")),
            "supply and demand zones read",
            "no supply/demand read",
        ),
        _institutional_check(structure, liquidity),
        _bool_check(
            "multi_timeframe_bias",
            bool(engines.get("mtf")),
            "higher-timeframe bias read (H4/H1)",
            "no multi-timeframe read",
        ),
        _regime_check(engines.get("volatility") or {}),
        _session_check(session_status),
        _news_check(news, now),
        _event_blackout_check(news.upcoming_events, now),
        _live_price_check(last_bar_ts, now, decision_timeframe),
    ]
    return EvidenceReport(checks=tuple(checks))


def _institutional_check(structure: dict[str, Any], liquidity: dict[str, Any]) -> EvidenceCheck:
    """Institutional behaviour, read off structure and liquidity: a sweep of a
    liquidity pool followed by displacement is the footprint. Advisory — its
    absence is ordinary, its presence is a signal the reader should see."""
    swept = bool(liquidity.get("sweeps") or liquidity.get("recent_sweep"))
    displaced = bool(structure.get("break_of_structure") or structure.get("displacement"))
    present = swept or displaced
    return EvidenceCheck(
        name="institutional_behavior",
        status="ok" if present else "warning",
        blocking=False,
        detail=(
            "liquidity sweep / displacement present"
            if present
            else "no clear sweep-and-displacement footprint"
        ),
        value={"sweep": swept, "displacement": displaced},
    )
