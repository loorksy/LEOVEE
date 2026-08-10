from __future__ import annotations

from app.engines.mtf import run_mtf_engine


def test_mtf_full_bullish_alignment() -> None:
    intel = {
        "D1": {"trend": "UP"},
        "H4": {"trend": "UP"},
        "H1": {"trend": "UP"},
    }
    mtf = run_mtf_engine(intel, stack=("D1", "H4", "H1"))
    assert mtf["alignment"] == "FULL_BULLISH"
    assert mtf["trade_bias"] == "BULLISH"


def test_mtf_mixed_bias() -> None:
    intel = {
        "D1": {"trend": "UP"},
        "H4": {"trend": "DOWN"},
        "H1": {"trend": "UP"},
    }
    mtf = run_mtf_engine(intel, stack=("D1", "H4", "H1"))
    assert mtf["alignment"].startswith("MIXED")
