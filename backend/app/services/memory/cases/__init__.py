"""Case memory: what gold has looked like before, and what came next.

Shared market history, deliberately not workspace-scoped — see
`app/models/market_case.py`. A workspace's own record lives in `strategy_stats`
behind RLS, and the two answer different questions.
"""

from app.services.memory.cases.fingerprint import (
    CaseFingerprint,
    fingerprint_at,
    fingerprint_similarity,
    fingerprint_vector,
    session_of,
)
from app.services.memory.cases.outcome import (
    MIN_STATS_SAMPLE,
    CaseResolution,
    ForwardOutcome,
    OutcomeStats,
    resolve_forward_outcome,
    summarize_outcomes,
)
from app.services.memory.cases.query import (
    MIN_SIMILARITY,
    SimilarCase,
    SimilarCaseResult,
    find_similar_cases,
)
from app.services.memory.cases.store import IndexedCase, build_cases, store_cases

__all__ = [
    "MIN_SIMILARITY",
    "MIN_STATS_SAMPLE",
    "CaseFingerprint",
    "CaseResolution",
    "ForwardOutcome",
    "IndexedCase",
    "OutcomeStats",
    "SimilarCase",
    "SimilarCaseResult",
    "build_cases",
    "find_similar_cases",
    "fingerprint_at",
    "fingerprint_similarity",
    "fingerprint_vector",
    "resolve_forward_outcome",
    "session_of",
    "store_cases",
    "summarize_outcomes",
]
