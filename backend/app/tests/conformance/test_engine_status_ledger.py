"""Keep app/engines/status.py honest about what is actually implemented.

The ledger drives the fail-closed gate in the orchestrator, so a wrong entry has
teeth in both directions: marking a placeholder IMPLEMENTED lets fabricated
evidence back into recommendations, and forgetting to flip a real engine leaves
the product degraded for no reason.
"""

from __future__ import annotations

import pytest

from app.agents import orchestrator
from app.engines.status import ENGINE_STATUS, EngineStatus, engine_unavailable, is_unavailable

pytestmark = pytest.mark.no_db

# Engines the orchestrator assembles into its evidence bundle. Kept here so a
# new engine cannot be added to the pipeline without a status decision.
EXPECTED_ENGINES = {
    "volatility",
    "structure",
    "geometry",
    "liquidity",
    "zones",
    "scenarios",
    "market_intelligence",
    "mtf",
    "risk",
    "decision",
}


def test_ledger_covers_exactly_the_pipeline_engines() -> None:
    assert set(ENGINE_STATUS) == EXPECTED_ENGINES, (
        "app/engines/status.py and the orchestrator's engine set have diverged; "
        "every engine in the pipeline needs an explicit status"
    )


def test_placeholder_helper_produces_a_recognisable_unavailable_payload() -> None:
    payload = engine_unavailable("zones")
    assert is_unavailable(payload)
    assert payload["engine"] == "zones"


def test_is_unavailable_does_not_match_real_engine_output() -> None:
    """A genuine result must never be mistaken for a declined one."""
    assert not is_unavailable({"bias": "BULLISH"})
    assert not is_unavailable({"status": "ok"})
    assert not is_unavailable(None)
    assert not is_unavailable("unavailable")


def test_orchestrator_gate_reads_the_same_notion_of_unavailable() -> None:
    """The gate and the engines must agree, or the fail-closed path never fires."""
    missing = orchestrator.unavailable_engines(
        {"zones": engine_unavailable("zones"), "volatility": {"regime": "NORMAL"}}
    )
    assert missing == ["zones"]


def test_progress_is_visible() -> None:
    """A running count, so the migration's progress is legible in CI output."""
    implemented = sorted(
        name for name, status in ENGINE_STATUS.items() if status is EngineStatus.IMPLEMENTED
    )
    placeholders = sorted(
        name for name, status in ENGINE_STATUS.items() if status is EngineStatus.PLACEHOLDER
    )
    print(f"\nengines implemented ({len(implemented)}): {', '.join(implemented)}")
    print(f"engines still placeholder ({len(placeholders)}): {', '.join(placeholders)}")
    assert implemented, "no engine is implemented — the ledger is certainly wrong"
