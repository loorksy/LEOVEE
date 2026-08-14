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
from app.schemas.engines import EngineName

pytestmark = pytest.mark.no_db

#: Derived, not listed. This used to be a third hand-written set of engine
#: names beside the ledger and the contract registry, and three copies of a list
#: do not check each other — they agree on the same omission. `plan_sanity` was
#: absent from both this set and the ledger for a whole phase while being one of
#: the engines the orchestrator actually runs, and the guard reported agreement.
#:
#: `EngineName` is the single authority for what an engine *is*, because it is
#: what `parse_engine_output` dispatches on. Anything the orchestrator assembles
#: that is not in it — the timeframe selection, the per-frame intelligence — is
#: not an engine and has no status to declare.
EXPECTED_ENGINES = {engine.value for engine in EngineName}


def test_ledger_covers_exactly_the_pipeline_engines() -> None:
    assert set(ENGINE_STATUS) == EXPECTED_ENGINES, (
        "app/engines/status.py and the engine contract registry have diverged; "
        "every engine needs an explicit status and a typed output contract"
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


#: Engines whose output describes the *market* and outlives the run that found
#: it. These are written to market artifact tables.
MARKET_ARTIFACT_ENGINES = {
    "structure",
    "volatility",
    "market_intelligence",
    "mtf",
    "liquidity",
    "zones",
    "geometry",
}

#: Engines whose output describes *this run's reasoning*. These belong to the
#: agent trace. Storing them as market artifacts would let a later retrieval
#: treat one run's opinion as an observed fact about the market.
RUN_SCOPED_ENGINES = {"scenarios", "risk", "plan_sanity", "decision"}


def test_every_engine_has_a_persistence_destination() -> None:
    """An engine in neither list is a gap, not a decision.

    Engine output that is written nowhere is invisible to episodic memory and to
    the learning loop, and nothing fails when it goes missing — which is how
    four engines' output was silently dropped until someone went looking.
    """
    classified = MARKET_ARTIFACT_ENGINES | RUN_SCOPED_ENGINES
    unclassified = set(ENGINE_STATUS) - classified
    assert not unclassified, (
        f"{sorted(unclassified)} produce output with no stated destination; add them to "
        "MARKET_ARTIFACT_ENGINES (written to market artifacts) or RUN_SCOPED_ENGINES "
        "(written to the agent trace)"
    )


def test_the_two_destinations_do_not_overlap() -> None:
    assert not (MARKET_ARTIFACT_ENGINES & RUN_SCOPED_ENGINES)


def test_every_degraded_reason_the_orchestrator_emits_is_in_the_contract() -> None:
    """A reason the schema cannot express is a reason nothing downstream can act on.

    The orchestrator builds its fail-closed payload as a raw dict, so a new
    reason string will not fail validation at the point it is written — it fails
    later, wherever something tries to parse the decision, or not at all. This
    keeps the two lists in step.
    """
    import re
    from pathlib import Path

    from app.agents.orchestrator import _DEGRADED_REASON_BY_KIND
    from app.schemas.decision import DegradedReason

    known = {reason.value for reason in DegradedReason}
    assert set(_DEGRADED_REASON_BY_KIND.values()) <= known

    source = (Path(__file__).resolve().parents[2] / "agents" / "orchestrator.py").read_text()
    literal_reasons = set(re.findall(r'fail_closed_no_trade\(\s*"([A-Z_]+)"', source))
    unknown = literal_reasons - known
    assert not unknown, f"orchestrator emits degraded reasons the contract lacks: {sorted(unknown)}"
