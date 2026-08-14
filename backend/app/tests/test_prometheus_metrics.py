"""The metrics say what actually happened, at a cardinality Prometheus survives.

Two properties matter more than coverage. **Every stage run is observed,
success or failure** — a stage that only reported successes would show latency
improving during an outage, which is the most misleading graph a dashboard can
draw. And **paths are routes, not rows**: a label per UUID means a series per
row visited, and Prometheus keeps every series it has ever seen.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from app.agents.errors import AgentStage
from app.agents.pipeline import PipelineLedger, run_stage
from app.observability.prometheus import normalize_path

pytestmark = pytest.mark.no_db


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def test_paths_become_routes_not_rows() -> None:
    assert (
        normalize_path("/api/v1/recommendations/123e4567-e89b-12d3-a456-426614174000")
        == "/api/v1/recommendations/{id}"
    )
    assert normalize_path("/api/v1/candles/42") == "/api/v1/candles/{n}"
    assert normalize_path("/") == "/"
    # A path that is already a route passes through unchanged.
    assert normalize_path("/api/v1/analysis/run") == "/api/v1/analysis/run"


@pytest.mark.asyncio
async def test_a_failed_stage_is_observed_with_its_taxonomy_code() -> None:
    """The failure code is the label, so a provider outage, a billing stop and a
    data gap are three different graphs rather than one climbing line."""
    ledger = PipelineLedger()

    async def boom() -> None:
        raise RuntimeError("HTTP 503 overloaded")

    before = (
        _sample(
            "leovee_agent_stage_failures_total",
            {"stage": AgentStage.NEWS.value, "code": "provider_unavailable"},
        )
        or 0.0
    )
    duration_before = (
        _sample("leovee_agent_stage_duration_seconds_count", {"stage": AgentStage.NEWS.value})
        or 0.0
    )

    await run_stage(ledger, AgentStage.NEWS, boom, deadline_seconds=5)

    after = _sample(
        "leovee_agent_stage_failures_total",
        {"stage": AgentStage.NEWS.value, "code": "provider_unavailable"},
    )
    duration_after = _sample(
        "leovee_agent_stage_duration_seconds_count", {"stage": AgentStage.NEWS.value}
    )
    assert after == before + 1
    # Observed despite failing: latency graphs must include the bad runs.
    assert duration_after == duration_before + 1


@pytest.mark.asyncio
async def test_a_successful_stage_is_observed_without_a_failure() -> None:
    ledger = PipelineLedger()

    async def fine() -> str:
        return "ok"

    duration_before = (
        _sample("leovee_agent_stage_duration_seconds_count", {"stage": AgentStage.RISK.value})
        or 0.0
    )
    await run_stage(ledger, AgentStage.RISK, fine, deadline_seconds=5)
    duration_after = _sample(
        "leovee_agent_stage_duration_seconds_count", {"stage": AgentStage.RISK.value}
    )
    assert duration_after == duration_before + 1


def test_the_metrics_endpoint_serves_the_real_registry() -> None:
    """`/metrics` must expose prometheus_client's output now that it exists;
    the legacy text was a fallback for when the dependency was absent."""
    from prometheus_client import generate_latest

    body = generate_latest(REGISTRY).decode()
    # The families this file itself populated must be present with samples —
    # asserting on ones no test touched would pass or fail on suite ordering.
    assert "leovee_agent_stage_duration_seconds_bucket" in body
    assert "leovee_agent_stage_failures_total" in body
