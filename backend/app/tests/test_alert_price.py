from __future__ import annotations

from app.services.alert_service import evaluate_price_alert


def test_price_alert_gte_triggers() -> None:
    assert evaluate_price_alert({"op": "gte", "price": 1.1}, 1.15) is True
    assert evaluate_price_alert({"op": "gte", "price": 1.1}, 1.05) is False


def test_price_alert_lte_triggers() -> None:
    assert evaluate_price_alert({"op": "lte", "price": 1.1}, 1.05) is True
