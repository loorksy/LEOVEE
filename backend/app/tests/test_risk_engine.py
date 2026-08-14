from decimal import Decimal

import pytest

from app.engines.risk import run_risk_engine


def test_risk_engine_approves_valid_setup() -> None:
    """Gold prices, because gold is the only thing this platform trades.

    The fixture used to be 1.1000/1.0980 — a currency pair, from before ADR
    0007. Under gold's pip size a two-pip currency stop is a fifth of a gold
    pip, so the test was measuring a market that does not exist here.
    """
    result = run_risk_engine(
        entry=Decimal("2000.00"),
        stop=Decimal("1996.00"),
        targets=[Decimal("2008.00")],
        account_risk_pct=Decimal("1"),
    )
    assert result["approved"] is True
    assert result["decision"] == "TRADE"
    assert result["direction"] == "BUY"
    assert result["position_size_units"] is not None
    # Gold pips, not currency pips: 4.00 at a pip of 0.01 is 400.
    assert result["risk_pips"] == 400.0
    assert result["reward_risk"] == 2.0


def test_a_short_plan_is_priced_as_a_short() -> None:
    """A stop above entry is a short, not an invalid stop.

    The signed subtraction that preceded this produced a negative distance and
    reported every short as unpriceable.
    """
    result = run_risk_engine(
        entry=Decimal("2000.00"),
        stop=Decimal("2004.00"),
        targets=[Decimal("1992.00")],
    )
    assert result["approved"] is True
    assert result["direction"] == "SELL"
    assert result["risk_pips"] == 400.0
    assert result["reward_risk"] == 2.0


def test_a_target_on_the_wrong_side_yields_no_ratio_rather_than_a_negative_one() -> None:
    """A negative reward:risk downstream reads as a very confident bad trade."""
    result = run_risk_engine(
        entry=Decimal("2000.00"),
        stop=Decimal("1996.00"),
        targets=[Decimal("1990.00")],
    )
    assert result["reward_risk"] is None


def test_risk_engine_rejects_invalid_stop() -> None:
    result = run_risk_engine(
        entry=Decimal("2000.00"),
        stop=Decimal("2000.00"),
    )
    assert result["approved"] is False
    assert result["decision"] == "NO_TRADE"


def test_sizing_carries_no_invented_cost() -> None:
    """Risk is the distance to the stop. Nothing is added to it.

    A thirty-pip gold spread used to be assumed here, inflating every size and —
    past three times the stop's own width — refusing the plan outright as
    `spread_too_wide`. That rejection came from a constant, not a market: this
    platform has no broker, places no order, and had never measured the number.
    One percent risked over a 4.00 stop is 1/400 of the account per unit, and
    the arithmetic says so exactly.
    """
    result = run_risk_engine(
        entry=Decimal("2000.00"),
        stop=Decimal("1996.00"),
        account_risk_pct=Decimal("1"),
    )
    assert result["position_size_units"] == pytest.approx(float(Decimal("0.01") / Decimal("4")))
    assert "spread_cost" not in result

    # And a stop tight enough that any assumed spread would have swallowed it is
    # still priced, not refused.
    tight = run_risk_engine(entry=Decimal("2000.00"), stop=Decimal("1999.95"))
    assert tight["approved"] is True
    assert tight["risk_pips"] == pytest.approx(5.0)
