from __future__ import annotations

from app.engines.reasoning import run_devils_advocate, run_reasoning_engine
from app.models.enums import RecommendationDirection


def test_adversarial_blocks_conflicting_mtf() -> None:
    decision = {"direction": RecommendationDirection.BUY.value, "confidence": 0.7}
    engines = {"mtf": {"trade_bias": "BEARISH"}}
    report = run_devils_advocate(decision=decision, engines=engines)
    assert report["approved"] is False
    reasoning = run_reasoning_engine(
        symbol="XAUUSD",
        decision=decision,
        engines=engines,
        adversarial=report,
    )
    assert reasoning["approved"] is False
    assert reasoning["status"] == "FORMING"
