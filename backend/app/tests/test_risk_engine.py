from decimal import Decimal

from app.engines.risk import run_risk_engine


def test_risk_engine_approves_valid_setup() -> None:
    """Gold prices, because gold is the only thing this platform trades.

    The fixture used to be 1.1000/1.0980 — a currency pair, from before ADR
    0007. Under gold's pip size a two-pip currency stop is a fifth of a gold
    pip, and the spread swallows it whole: the engine correctly refuses, and the
    test was measuring a market that does not exist here.
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
