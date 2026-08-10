from decimal import Decimal

from app.engines.risk import run_risk_engine


def test_risk_engine_approves_valid_setup() -> None:
    result = run_risk_engine(
        entry=Decimal("1.1000"),
        stop=Decimal("1.0980"),
        account_risk_pct=Decimal("1"),
    )
    assert result["approved"] is True
    assert result["decision"] == "TRADE"
    assert result["position_size_units"] is not None


def test_risk_engine_rejects_invalid_stop() -> None:
    result = run_risk_engine(
        entry=Decimal("1.1000"),
        stop=Decimal("1.1000"),
    )
    assert result["approved"] is False
    assert result["decision"] == "NO_TRADE"
