from __future__ import annotations

from typing import Any


def run_scenario_engine(
    structure: dict[str, Any],
    volatility: dict[str, Any],
    liquidity: dict[str, Any],
) -> dict[str, Any]:
    bias = structure.get("bias", "NEUTRAL")
    scenarios = [
        {
            "label": "BULLISH",
            "confidence": 0.55 if bias == "BULLISH" else 0.35,
            "evidence": {"structure": structure, "volatility": volatility},
        },
        {
            "label": "BEARISH",
            "confidence": 0.55 if bias == "BEARISH" else 0.35,
            "evidence": {"structure": structure, "liquidity": liquidity},
        },
        {
            "label": "NO_TRADE",
            "confidence": 0.4 if volatility.get("bucket") == "HIGH" else 0.2,
            "evidence": {"volatility": volatility},
        },
    ]
    return {"scenarios": scenarios}
