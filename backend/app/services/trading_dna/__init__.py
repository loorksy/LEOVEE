"""Behavioural analytics over the reader's own record.

Not market analysis — the market has its own memory (`services/memory/cases`).
This is about the analyst: what their plans did, and what they did about them.

Eight of the reference implementation's eighteen metrics are dropped rather than
approximated, because every one of them assumed execution data a platform that
places no orders does not have. See `types.py` for the list and the reason.
"""

from app.services.trading_dna.metrics import MINIMUM_SAMPLES, compute_metrics
from app.services.trading_dna.persona import (
    DOMINANCE_GATE,
    MIN_PERSONA_SAMPLE,
    derive_persona,
)
from app.services.trading_dna.types import (
    DnaMetric,
    EvidenceBundle,
    EvidenceReferences,
    EvidenceStatus,
    MetricKey,
    PersonaName,
    PlanRecord,
    TradeRecord,
    TradingPersona,
)

__all__ = [
    "DOMINANCE_GATE",
    "MINIMUM_SAMPLES",
    "MIN_PERSONA_SAMPLE",
    "DnaMetric",
    "EvidenceBundle",
    "EvidenceReferences",
    "EvidenceStatus",
    "MetricKey",
    "PersonaName",
    "PlanRecord",
    "TradeRecord",
    "TradingPersona",
    "compute_metrics",
    "derive_persona",
]
