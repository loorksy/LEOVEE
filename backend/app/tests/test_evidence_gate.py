"""The evidence gate: what must be read before a direction is published.

The gate is the deterministic form of a product rule — "the agent reads the
session, the news, the liquidity and the live price before it decides". These
tests pin which readings block publication and which only warn, and that a
blocked run names the reason rather than degrading silently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.engines.evidence import (
    EconomicEvent,
    EvidenceReport,
    NewsContext,
    assess_evidence,
)
from app.models.enums import Timeframe

pytestmark = pytest.mark.no_db

_NOW = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)  # inside the New York session

_FULL_ENGINES = {
    "structure": {"bias": "bullish", "break_of_structure": True},
    "liquidity": {"sweeps": [{"level": 2000.0}]},
    "zones": {"zones": [{"type": "DEMAND"}]},
    "mtf": {"trade_bias": "bullish"},
    "volatility": {"regime": "trend"},
}

_OPEN_SESSION = {"session": "newyork", "is_open": True}

_FRESH_NEWS = NewsContext(
    provider_configured=True,
    headline_count=5,
    latest_headline_ts=_NOW - timedelta(minutes=30),
)


def _assess(**overrides: Any) -> EvidenceReport:
    kwargs: dict[str, Any] = {
        "engines": _FULL_ENGINES,
        "session_status": _OPEN_SESSION,
        "news": _FRESH_NEWS,
        "last_bar_ts": _NOW - timedelta(minutes=1),
        "now": _NOW,
        "decision_timeframe": Timeframe.M15,
    }
    kwargs.update(overrides)
    return assess_evidence(**kwargs)


def test_a_complete_fresh_read_is_not_blocked() -> None:
    report = _assess()
    assert report.blocked is False
    assert report.block_reason is None
    names = {c.name for c in report.checks}
    # Every reading the owner asked for is present in the checklist.
    assert {
        "market_structure",
        "liquidity_map",
        "supply_demand",
        "institutional_behavior",
        "multi_timeframe_bias",
        "volatility_regime",
        "trading_session",
        "market_intelligence",
        "event_blackout",
        "live_price",
    } <= names


def test_a_closed_market_blocks_the_recommendation() -> None:
    report = _assess(session_status={"session": "weekend", "is_open": False})
    assert report.blocked is True
    assert report.block_reason == "EVIDENCE_TRADING_SESSION"


def test_a_stale_price_blocks_it_named() -> None:
    # M15 tolerates 3 bars = 45 min; 90 minutes is stale.
    report = _assess(last_bar_ts=_NOW - timedelta(minutes=90))
    assert report.blocked is True
    assert report.block_reason == "EVIDENCE_LIVE_PRICE"


def test_a_fresh_price_within_the_window_passes() -> None:
    report = _assess(last_bar_ts=_NOW - timedelta(minutes=44))
    live = next(c for c in report.checks if c.name == "live_price")
    assert live.status == "ok"


def test_an_imminent_high_impact_event_blacks_out_the_scalp() -> None:
    news = NewsContext(
        provider_configured=True,
        headline_count=3,
        latest_headline_ts=_NOW,
        upcoming_events=(
            EconomicEvent(ts=_NOW + timedelta(minutes=8), title="US CPI", impact="high"),
        ),
    )
    report = _assess(news=news)
    assert report.blocked is True
    assert report.block_reason == "EVIDENCE_EVENT_BLACKOUT"


def test_a_distant_event_does_not_block() -> None:
    news = NewsContext(
        provider_configured=True,
        headline_count=3,
        latest_headline_ts=_NOW,
        upcoming_events=(
            EconomicEvent(ts=_NOW + timedelta(hours=6), title="US CPI", impact="high"),
        ),
    )
    report = _assess(news=news)
    assert report.blocked is False


def test_a_medium_impact_event_does_not_black_out() -> None:
    news = NewsContext(
        provider_configured=True,
        headline_count=3,
        latest_headline_ts=_NOW,
        upcoming_events=(
            EconomicEvent(ts=_NOW + timedelta(minutes=5), title="Jobless claims", impact="medium"),
        ),
    )
    assert _assess(news=news).blocked is False


def test_missing_news_provider_warns_but_never_blocks() -> None:
    news = NewsContext(provider_configured=False, headline_count=0, latest_headline_ts=None)
    report = _assess(news=news)
    assert report.blocked is False
    intel = next(c for c in report.checks if c.name == "market_intelligence")
    assert intel.status == "warning"
    assert intel.blocking is False
    assert "market_intelligence" in report.warnings


def test_a_missing_liquidity_read_blocks() -> None:
    engines = {**_FULL_ENGINES, "liquidity": {}}
    report = _assess(engines=engines)
    assert report.blocked is True
    assert report.block_reason == "EVIDENCE_LIQUIDITY_MAP"


def test_a_quiet_regime_warns_but_does_not_block() -> None:
    engines = {**_FULL_ENGINES, "volatility": {"regime": "dead"}}
    report = _assess(engines=engines)
    assert report.blocked is False
    assert "volatility_regime" in report.warnings


def test_the_report_serializes_for_the_ui() -> None:
    payload = _assess().to_dict()
    assert set(payload) == {"blocked", "block_reason", "warnings", "checks"}
    assert all(
        {"name", "status", "blocking", "detail", "value"} <= set(c) for c in payload["checks"]
    )
