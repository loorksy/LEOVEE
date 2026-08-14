"""The process's real metrics: Prometheus collectors for everything worth graphing.

This replaces hand-rolled in-memory counters that had two quiet failure modes.
They vanished on every restart, so a deploy looked like traffic dropping to
zero; and they could only sum durations, so "the p95 got slow" — the question
an operator actually asks — was unanswerable from the data collected.

**Cardinality is a budget, and paths are normalised before they become labels.**
A label per raw URL means a label per UUID, and Prometheus keeps every series it
has ever seen: one crawler walking `/api/v1/recommendations/<uuid>` mints
thousands of series and the scrape slows for everyone. The normaliser collapses
identifiers before anything reaches a collector.

**Agent-stage failures are labelled by the taxonomy** (`app/agents/errors`), so
the dashboard can distinguish a provider outage from a billing stop from a data
gap. One `errors_total` counter with no cause label answers "is it broken?" and
nothing else, and "is it broken?" was never the hard question.
"""

from __future__ import annotations

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

__all__ = [
    "registry",
    "http_requests_total",
    "http_request_duration_seconds",
    "agent_stage_duration_seconds",
    "agent_stage_failures_total",
    "engine_duration_seconds",
    "tool_loop_iterations",
    "llm_tokens_total",
    "recommendation_outcomes_total",
    "reevaluation_triggers_total",
    "build_info",
]

#: The default registry, exposed under a name so tests can construct their own
#: isolated `CollectorRegistry` instead of scraping global state.
registry: CollectorRegistry = REGISTRY

#: Buckets shaped for an API in front of a database: most requests land in the
#: tens of milliseconds, the interesting tail is 0.5–5s, and anything past ten
#: seconds is an outage, not a distribution.
_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

#: Agent stages call models: seconds, not milliseconds, and a long tail that is
#: normal rather than pathological.
_STAGE_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 80.0)

http_requests_total = Counter(
    "leovee_http_requests_total",
    "HTTP requests handled, by normalised path",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "leovee_http_request_duration_seconds",
    "HTTP request latency, by normalised path",
    ["method", "path"],
    buckets=_HTTP_BUCKETS,
)

agent_stage_duration_seconds = Histogram(
    "leovee_agent_stage_duration_seconds",
    "Wall time per agent pipeline stage",
    ["stage"],
    buckets=_STAGE_BUCKETS,
)

agent_stage_failures_total = Counter(
    "leovee_agent_stage_failures_total",
    "Stage failures, labelled by the failure taxonomy so a provider outage, a "
    "billing stop and a data gap are three different graphs",
    ["stage", "code"],
)

engine_duration_seconds = Histogram(
    "leovee_engine_duration_seconds",
    "Wall time per deterministic engine",
    ["engine"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

tool_loop_iterations = Histogram(
    "leovee_tool_loop_iterations",
    "Tool calls consumed by one decision-stage conversation",
    buckets=(0, 1, 2, 3, 5, 8, 13),
)

llm_tokens_total = Counter(
    "leovee_llm_tokens_total",
    "Tokens spent, by provider, model and direction (prompt/completion)",
    ["provider", "model", "direction"],
)

recommendation_outcomes_total = Counter(
    "leovee_recommendation_outcomes_total",
    "Terminal recommendation outcomes recorded by the learning loop",
    ["outcome", "kind"],
)

reevaluation_triggers_total = Counter(
    "leovee_reevaluation_triggers_total",
    "Re-evaluation triggers, by reason and what became of them",
    ["reason", "outcome"],
)

embedding_fallback_total = Counter(
    "leovee_embedding_fallback_total",
    "Times a memory vector was indexed with the deterministic (hashed) fallback "
    "because no embedding provider was configured — every increment is noise "
    "entering the semantic index",
)

worker_job_failures_total = Counter(
    "leovee_worker_job_failures_total",
    "Background job failures, by job name and exception type — a chronically "
    "failing cron is otherwise invisible",
    ["job", "code"],
)

build_info = Gauge(
    "leovee_build_info",
    "Constant 1, labelled with the running version — join against it to slice "
    "any other metric by deploy",
    ["version"],
)


def record_embedding_fallback() -> None:
    embedding_fallback_total.inc()


def record_worker_job_failure(job: str, code: str) -> None:
    worker_job_failures_total.labels(job=job, code=code).inc()


def normalize_path(path: str) -> str:
    """Collapse identifiers so a path is a route, not a row.

    UUIDs and bare numbers become placeholders. Kept deliberately dumb — a
    regex zoo here would itself become a maintenance surface — and centralised
    so the counter and the histogram can never disagree about what a path is.
    """
    parts = [part for part in path.split("/") if part]
    normalized: list[str] = []
    for part in parts:
        if len(part) == 36 and part.count("-") == 4:
            normalized.append("{id}")
        elif part.isdigit():
            normalized.append("{n}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized) if normalized else "/"
