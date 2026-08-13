"""The gold-only allowlist and the session calendar.

The calendar tests are written around specific instants rather than "now",
because the whole point of the port is DST correctness and a test that reads the
clock only exercises whichever half of the year it happens to run in.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.symbols import (
    DEFAULT_SYMBOL,
    GOLD,
    TRADABLE_SYMBOLS,
    UnknownSymbolError,
    instrument_for,
    is_tradable,
    normalize_symbol,
    pip_size,
    require_instrument,
)
from app.services.market.calendar import (
    TradingClass,
    get_session_status,
    is_expected_daily_bar_open,
    is_market_open_at,
    resolve_trading_class,
)

pytestmark = pytest.mark.no_db

XAU = "XAUUSD"

# Kept out of the gold-only sweep below: these must stay rejected.
_REJECTED = ("EURUSD", "GBPUSD", "XAGUSD", "BTCUSD")


class TestAllowlist:
    def test_gold_is_the_entire_universe(self) -> None:
        assert TRADABLE_SYMBOLS == ("XAUUSD",)
        assert DEFAULT_SYMBOL == "XAUUSD"

    @pytest.mark.parametrize(
        "raw", ["XAUUSD", "xauusd", "XAU/USD", "xau_usd", "XAU-USD", " XAU USD "]
    )
    def test_spellings_normalise_to_the_same_instrument(self, raw: str) -> None:
        # OANDA writes XAU_USD, users write XAU/USD; punctuation must not be a
        # way around the allowlist.
        assert normalize_symbol(raw) == "XAUUSD"
        assert is_tradable(raw)
        assert instrument_for(raw) is GOLD

    @pytest.mark.parametrize(
        "raw", [_REJECTED[0], _REJECTED[1], _REJECTED[2], _REJECTED[3], "", "XAU"]
    )
    def test_everything_else_is_rejected(self, raw: str) -> None:
        assert not is_tradable(raw)
        assert instrument_for(raw) is None

    def test_require_instrument_raises_rather_than_substituting_gold(self) -> None:
        # Quietly answering about gold when asked about EURUSD would produce a
        # confident analysis of the wrong market.
        with pytest.raises(UnknownSymbolError) as caught:
            require_instrument(_REJECTED[0])
        assert _REJECTED[0] in str(caught.value)
        assert "XAUUSD" in str(caught.value)

    def test_gold_prices_to_two_decimals(self) -> None:
        # pip_location is an exponent, and the FX default of -4 would scale
        # every stop distance and position size by a hundred.
        assert GOLD.pip_location == -2
        assert pip_size(XAU) == pytest.approx(0.01)
        assert pip_size(_REJECTED[0]) is None

    def test_oanda_instrument_mapping(self) -> None:
        assert GOLD.oanda_instrument == "XAU_USD"
        assert GOLD.asset_class == "METAL"


class TestTradingClass:
    def test_gold_is_a_metal(self) -> None:
        assert resolve_trading_class(XAU) is TradingClass.METAL

    def test_unknown_symbols_fall_back_conservatively(self) -> None:
        assert resolve_trading_class(_REJECTED[0]) is TradingClass.UNKNOWN


class TestWeekBoundaries:
    """Sunday 18:00 NY open, Friday 17:00 NY close — in wall time, not UTC."""

    def test_closed_on_saturday(self) -> None:
        assert not is_market_open_at(XAU, datetime(2026, 3, 7, 12, 0, tzinfo=UTC))

    def test_closed_before_sunday_open(self) -> None:
        # 21:00 UTC on 2026-03-08 is 17:00 NY (EDT) — FX has opened, gold has not.
        assert not is_market_open_at(XAU, datetime(2026, 3, 8, 21, 30, tzinfo=UTC))

    def test_open_after_sunday_gold_open(self) -> None:
        # 22:00 UTC = 18:00 NY under EDT.
        assert is_market_open_at(XAU, datetime(2026, 3, 8, 22, 30, tzinfo=UTC))

    def test_open_during_the_week(self) -> None:
        assert is_market_open_at(XAU, datetime(2026, 3, 11, 12, 0, tzinfo=UTC))

    def test_closed_after_friday_close(self) -> None:
        # 21:00 UTC Friday = 17:00 NY under EDT.
        assert not is_market_open_at(XAU, datetime(2026, 3, 13, 21, 30, tzinfo=UTC))

    def test_open_just_before_friday_close(self) -> None:
        assert is_market_open_at(XAU, datetime(2026, 3, 13, 20, 30, tzinfo=UTC))


class TestDaylightSaving:
    """The bug the reference implementation's comments describe.

    A fixed 22:00 UTC boundary is right in winter and an hour wrong in summer.
    These pairs sit on the same NY wall clock either side of a DST transition,
    so a fixed-offset implementation gets exactly one of each pair wrong.
    """

    def test_friday_close_holds_under_est(self) -> None:
        # 2026-01-16, EST: 17:00 NY = 22:00 UTC.
        assert is_market_open_at(XAU, datetime(2026, 1, 16, 21, 30, tzinfo=UTC))
        assert not is_market_open_at(XAU, datetime(2026, 1, 16, 22, 30, tzinfo=UTC))

    def test_friday_close_holds_under_edt(self) -> None:
        # 2026-06-19, EDT: 17:00 NY = 21:00 UTC — an hour earlier than winter.
        assert not is_market_open_at(XAU, datetime(2026, 6, 19, 21, 30, tzinfo=UTC))
        assert is_market_open_at(XAU, datetime(2026, 6, 19, 20, 30, tzinfo=UTC))

    def test_sunday_open_holds_under_est(self) -> None:
        # 2026-01-18, EST: gold opens 18:00 NY = 23:00 UTC.
        assert not is_market_open_at(XAU, datetime(2026, 1, 18, 22, 30, tzinfo=UTC))
        assert is_market_open_at(XAU, datetime(2026, 1, 18, 23, 30, tzinfo=UTC))

    def test_spring_forward_weekend(self) -> None:
        # DST begins 2026-03-08 in the US; the Sunday open still lands on the
        # 18:00 NY wall clock, which is 22:00 UTC that night.
        assert not is_market_open_at(XAU, datetime(2026, 3, 8, 21, 0, tzinfo=UTC))
        assert is_market_open_at(XAU, datetime(2026, 3, 8, 22, 0, tzinfo=UTC))

    def test_fall_back_weekend(self) -> None:
        # DST ends 2026-11-01; the open moves back to 23:00 UTC.
        assert not is_market_open_at(XAU, datetime(2026, 11, 1, 22, 0, tzinfo=UTC))
        assert is_market_open_at(XAU, datetime(2026, 11, 1, 23, 0, tzinfo=UTC))


class TestMaintenanceBreak:
    """Gold halts [17:00, 18:00) NY on weekdays — four bars a day on 15m."""

    def test_halted_during_the_break(self) -> None:
        # Wednesday 2026-03-11, 21:30 UTC = 17:30 NY (EDT).
        assert not is_market_open_at(XAU, datetime(2026, 3, 11, 21, 30, tzinfo=UTC))

    def test_open_immediately_before_the_break(self) -> None:
        assert is_market_open_at(XAU, datetime(2026, 3, 11, 20, 59, tzinfo=UTC))

    def test_open_immediately_after_the_break(self) -> None:
        assert is_market_open_at(XAU, datetime(2026, 3, 11, 22, 1, tzinfo=UTC))

    def test_break_follows_wall_time_across_dst(self) -> None:
        # Same wall-clock break, different UTC hour in winter.
        assert not is_market_open_at(XAU, datetime(2026, 1, 14, 22, 30, tzinfo=UTC))
        assert is_market_open_at(XAU, datetime(2026, 1, 14, 21, 30, tzinfo=UTC))


class TestDailyBarExpectation:
    def test_daily_bars_open_at_the_new_york_close_hour(self) -> None:
        # Monday 2026-03-09, 21:00 UTC = 17:00 NY (EDT).
        assert is_expected_daily_bar_open(XAU, datetime(2026, 3, 9, 21, 0, tzinfo=UTC))

    def test_no_daily_bar_at_the_wrong_hour(self) -> None:
        assert not is_expected_daily_bar_open(XAU, datetime(2026, 3, 9, 12, 0, tzinfo=UTC))

    def test_no_daily_bar_opens_on_friday_or_saturday(self) -> None:
        # Sunday–Thursday opens cover the Monday–Friday sessions: five a week.
        assert not is_expected_daily_bar_open(XAU, datetime(2026, 3, 13, 21, 0, tzinfo=UTC))
        assert not is_expected_daily_bar_open(XAU, datetime(2026, 3, 14, 21, 0, tzinfo=UTC))

    def test_a_normal_week_has_exactly_five_daily_bars(self) -> None:
        # This is the assertion the phantom-gap bug would fail: a fixed-UTC
        # boundary yields four or six here depending on the season.
        start = datetime(2026, 3, 8, 0, 0, tzinfo=UTC)
        expected = sum(
            is_expected_daily_bar_open(XAU, datetime.fromtimestamp(ts, tz=UTC))
            for ts in range(int(start.timestamp()), int(start.timestamp()) + 7 * 86400, 3600)
        )
        assert expected == 5

    def test_a_summer_week_also_has_five(self) -> None:
        start = datetime(2026, 6, 14, 0, 0, tzinfo=UTC)
        expected = sum(
            is_expected_daily_bar_open(XAU, datetime.fromtimestamp(ts, tz=UTC))
            for ts in range(int(start.timestamp()), int(start.timestamp()) + 7 * 86400, 3600)
        )
        assert expected == 5


class TestSessionStatus:
    @pytest.mark.parametrize(
        ("moment", "expected"),
        [
            (datetime(2026, 3, 11, 12, 0, tzinfo=UTC), "MARKET_OPEN"),
            (datetime(2026, 3, 7, 12, 0, tzinfo=UTC), "WEEKEND"),
            (datetime(2026, 3, 13, 21, 30, tzinfo=UTC), "WEEK_CLOSED"),
            (datetime(2026, 3, 8, 12, 0, tzinfo=UTC), "WEEK_NOT_OPEN_YET"),
            (datetime(2026, 3, 11, 21, 30, tzinfo=UTC), "DAILY_MAINTENANCE_BREAK"),
        ],
    )
    def test_reason_codes(self, moment: datetime, expected: str) -> None:
        assert get_session_status(XAU, moment).reason == expected

    def test_reasons_are_machine_readable_not_prose(self) -> None:
        # Translation lives in the frontend dictionary; a backend that returns
        # one language cannot serve an Arabic-default UI.
        status = get_session_status(XAU, datetime(2026, 3, 7, 12, 0, tzinfo=UTC))
        assert status.reason.isupper()
        assert " " not in status.reason

    def test_naive_datetimes_are_treated_as_utc(self) -> None:
        aware = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
        naive = datetime(2026, 3, 7, 12, 0)  # noqa: DTZ001 — the case under test
        assert is_market_open_at(XAU, naive) == is_market_open_at(XAU, aware)
