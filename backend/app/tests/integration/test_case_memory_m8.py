"""Indexing and retrieving market cases end to end.

The exit criterion this covers is the one the migration plan names: a
fingerprinted historical window retrieves its known analogues. The tests that
matter most are the ones about *not* retrieving — a memory that always has an
answer is not evidence, and one that can see the future is worse than none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.bar import OHLCBar
from app.models.market_case import MarketCase
from app.services import market_data
from app.services.memory.cases import (
    MIN_STATS_SAMPLE,
    CaseFingerprint,
    build_cases,
    find_similar_cases,
    fingerprint_at,
    store_cases,
)

EPOCH = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


def _walk(
    *, seed: int, count: int, start: float = 2000.0, drift: float = 0.0, vol: float = 0.6
) -> list[OHLCBar]:
    """A deterministic walk. Seeded, because a memory test that resamples every
    run tells you about the sampler."""
    state = seed or 1

    def rand() -> float:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        return state / 0x100000000

    bars: list[OHLCBar] = []
    price = start
    for index in range(count):
        open_ = price
        price = open_ + drift + (rand() - 0.5) * vol * 2
        bars.append(
            OHLCBar(
                ts=EPOCH + timedelta(minutes=15 * index),
                open=open_,
                high=max(open_, price) + rand() * vol,
                low=min(open_, price) - rand() * vol,
                close=price,
            )
        )
    return bars


async def _indexed(session: AsyncSession, bars: list[OHLCBar], *, timeframe: str = "M15") -> int:
    symbol = await market_data.get_or_create_symbol(session, "XAUUSD")
    cases = build_cases(bars)
    return await store_cases(session, cases, symbol_id=symbol.id, timeframe=timeframe)


@pytest.mark.asyncio
async def test_a_swept_window_becomes_cases_with_both_directions_resolved(
    db_session: AsyncSession,
) -> None:
    """A moment is not bullish or bearish in itself.

    Indexing only the side the market happened to take would build a memory that
    always agrees with what came next.
    """
    written = await _indexed(db_session, _walk(seed=7, count=260, drift=0.25))
    assert written > 0

    rows = list((await db_session.execute(select(MarketCase))).scalars().all())
    assert len(rows) == written
    assert all(row.buy_resolution and row.sell_resolution for row in rows)
    assert all(row.embedding is not None and len(row.embedding) == 8 for row in rows)


@pytest.mark.asyncio
async def test_only_moments_with_a_full_horizon_are_indexed(db_session: AsyncSession) -> None:
    """Truncated cases would concentrate at the recent end.

    A moment with twelve bars ahead of it records `unresolved` as though the
    market declined to answer, when the question was cut short — and those rows
    would sit exactly where the memory is consulted most.
    """
    bars = _walk(seed=9, count=200, drift=0.2)
    await _indexed(db_session, bars)

    newest = await db_session.scalar(select(func.max(MarketCase.case_ts)))
    assert newest is not None
    # The last 40 bars are the horizon of the newest case, so nothing may be
    # indexed inside them.
    assert newest <= bars[-41].ts


@pytest.mark.asyncio
async def test_re_sweeping_updates_rather_than_duplicates(db_session: AsyncSession) -> None:
    """A nightly job re-reading the last week must not multiply that week."""
    bars = _walk(seed=11, count=220, drift=0.2)
    first = await _indexed(db_session, bars)
    second = await _indexed(db_session, bars)
    total = await db_session.scalar(select(func.count()).select_from(MarketCase))

    assert first == second
    assert total == first


@pytest.mark.asyncio
async def test_a_window_retrieves_its_own_analogues(db_session: AsyncSession) -> None:
    """The exit criterion: fingerprint a window, get back moments that match it."""
    bars = _walk(seed=13, count=400, drift=0.2)
    await _indexed(db_session, bars)
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")

    probe = fingerprint_at(bars[:300])
    assert probe is not None

    result = await find_similar_cases(
        db_session, symbol_id=symbol.id, timeframe="M15", fingerprint=probe, direction="buy"
    )
    assert result.candidates_considered > 0
    assert result.cases, "a window drawn from the indexed series must match something"
    # Ranked on the exact metric, descending, and every result clears the floor.
    similarities = [case.similarity for case in result.cases]
    assert similarities == sorted(similarities, reverse=True)
    assert min(similarities) >= 0.72


@pytest.mark.asyncio
async def test_an_unlike_moment_returns_nothing_rather_than_its_nearest_miss(
    db_session: AsyncSession,
) -> None:
    """A memory that always answers is not evidence.

    The vector index will always hand back *something* — it ranks by distance,
    not by whether the distance is small. The similarity floor is what turns
    "closest available" back into "actually comparable".
    """
    await _indexed(db_session, _walk(seed=17, count=300, drift=0.3, vol=0.4))
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")

    # Same trend, so it survives the categorical prefilter and reaches the exact
    # pass — and is then rejected there, which is the behaviour under test.
    alien = CaseFingerprint(
        regime="range",
        trend="up",
        range_zone="near_low",
        pullback_depth=1.0,
        impulse_atr=0.0,
        volatility=0.05,
        session="asia",
        structure_run=0,
    )
    result = await find_similar_cases(
        db_session, symbol_id=symbol.id, timeframe="M15", fingerprint=alien, direction="buy"
    )
    assert result.candidates_considered > 0, "the prefilter must have offered candidates"
    assert result.cases == []
    assert result.stats.sample_size == 0
    assert result.stats.hit_rate is None


@pytest.mark.asyncio
async def test_a_thin_match_reports_counts_and_withholds_rates(
    db_session: AsyncSession,
) -> None:
    bars = _walk(seed=19, count=400, drift=0.2)
    await _indexed(db_session, bars)
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    probe = fingerprint_at(bars[:300])
    assert probe is not None

    result = await find_similar_cases(
        db_session,
        symbol_id=symbol.id,
        timeframe="M15",
        fingerprint=probe,
        direction="buy",
        limit=MIN_STATS_SAMPLE - 1,
    )
    assert result.stats.sample_size <= MIN_STATS_SAMPLE - 1
    if result.stats.sample_size:
        assert result.stats.hit_rate is None
        assert result.stats.sufficient is False


@pytest.mark.asyncio
async def test_the_memory_cannot_be_asked_about_the_future(db_session: AsyncSession) -> None:
    """Retrieving cases from after the analysed moment is the one way a
    backtest-free platform can still fool itself."""
    bars = _walk(seed=23, count=400, drift=0.2)
    await _indexed(db_session, bars)
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    probe = fingerprint_at(bars[:300])
    assert probe is not None

    cutoff = bars[150].ts
    result = await find_similar_cases(
        db_session,
        symbol_id=symbol.id,
        timeframe="M15",
        fingerprint=probe,
        direction="buy",
        exclude_from=cutoff,
    )
    assert all(case.case_ts < cutoff for case in result.cases)


@pytest.mark.asyncio
async def test_a_different_timeframe_is_a_different_memory(db_session: AsyncSession) -> None:
    """An M1 moment and an M15 moment are not comparable however alike they look."""
    await _indexed(db_session, _walk(seed=29, count=300, drift=0.2), timeframe="M15")
    symbol = await market_data.get_or_create_symbol(db_session, "XAUUSD")
    probe = fingerprint_at(_walk(seed=29, count=300, drift=0.2)[:250])
    assert probe is not None

    result = await find_similar_cases(
        db_session, symbol_id=symbol.id, timeframe="M1", fingerprint=probe, direction="buy"
    )
    assert result.candidates_considered == 0
    assert result.cases == []
