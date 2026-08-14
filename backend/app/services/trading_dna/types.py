"""What the DNA can say, and what it must refuse to say.

Behavioural analytics over the reader's **own** record: their plans, how those
plans resolved, and the trades they reported taking. Not market analysis — the
market has its own memory (`services/memory/cases`). This is about the analyst.

**Eight of the reference's eighteen metrics are not computable here, and they are
dropped rather than approximated.** Every one of them silently assumed execution
data that does not exist on a platform that places no orders (D4):

- `execution_consistency` — variance of spread, slippage and commission. Not
  merely unmeasured: modelling any of them is forbidden outright (ADR 0010).
- `risk_tolerance`, `risk_scaling` — position-sizing telemetry recorded at fill.
  Nothing here sizes a position or opens one.
- `break_even_behavior`, `trailing_behavior` — stop-management actions taken on
  a live position. With no position there is nothing to manage.
- `preferred_symbols`, `portfolio_concentration` — with XAUUSD the only
  instrument (D10) the answer is `[{XAUUSD: 1.0}]` and a Herfindahl index of
  exactly 1, forever. A metric with one possible value is not a measurement.
- `backtest_coverage` — a reference to a research job that does not exist (D7).

Approximating any of these would produce a number that *looks* like behavioural
insight and is actually an artefact of the platform's own shape. A dropped
metric is honest; an invented one is the class of defect this whole migration
has been removing.

**Every metric is supported or explicitly insufficient.** There is no third
state and no default value. A metric computed from four samples and presented
beside one computed from four hundred, with nothing to tell them apart, is how a
profile becomes confident about a person it has barely observed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

__all__ = [
    "MetricKey",
    "EvidenceStatus",
    "EvidenceReferences",
    "DnaMetric",
    "PersonaName",
    "TradingPersona",
    "PlanRecord",
    "TradeRecord",
    "EvidenceBundle",
]


class MetricKey(StrEnum):
    """The ten metrics this platform can actually measure."""

    AVERAGE_R = "average_r"
    WIN_LOSS_RATIO = "win_loss_ratio"
    TIME_TO_TERMINAL = "time_to_terminal"
    MAE_R = "mae_r"
    MFE_R = "mfe_r"
    CONFIDENCE_CALIBRATION = "confidence_calibration"
    DIRECTION_BIAS = "direction_bias"
    SESSION_PREFERENCE = "session_preference"
    TIMEFRAME_PREFERENCE = "timeframe_preference"
    FOLLOW_THROUGH = "follow_through"


class EvidenceStatus(StrEnum):
    SUPPORTED = "supported"
    #: Named rather than absent: "we have not seen enough of this yet" is
    #: information, and a missing key reads as a bug.
    INSUFFICIENT = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class EvidenceReferences:
    """Exactly which rows produced a number.

    Not decoration. A conclusion the reader cannot trace back to the plans it
    came from is one they have to take on faith, and this profile is an argument
    about *them* — the least appropriate place to ask for faith.
    """

    recommendation_ids: tuple[str, ...] = ()
    outcome_ids: tuple[str, ...] = ()
    trade_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_ids": list(self.recommendation_ids),
            "outcome_ids": list(self.outcome_ids),
            "trade_ids": list(self.trade_ids),
        }


@dataclass(frozen=True, slots=True)
class DnaMetric:
    key: MetricKey
    status: EvidenceStatus
    #: Present only when supported. `None` on an insufficient metric is the
    #: point: there is no value to round, compare or plot.
    value: float | None = None
    #: A distribution, for the preference metrics. Shares sum to 1.
    breakdown: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0
    required_sample: int = 0
    references: EvidenceReferences = field(default_factory=EvidenceReferences)

    @property
    def supported(self) -> bool:
        return self.status is EvidenceStatus.SUPPORTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key.value,
            "status": self.status.value,
            "value": self.value,
            "breakdown": dict(self.breakdown),
            "sample_size": self.sample_size,
            "required_sample": self.required_sample,
            "references": self.references.to_dict(),
        }


class PersonaName(StrEnum):
    SCALPER = "scalper"
    INTRADAY = "intraday"
    SWING = "swing"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class TradingPersona:
    name: PersonaName
    #: Reason code; the words are chosen where the reader's language is known.
    reason: str
    sample_size: int
    support: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "reason": self.reason,
            "sample_size": self.sample_size,
            "support": self.support,
        }


@dataclass(frozen=True, slots=True)
class PlanRecord:
    """One closed plan, flattened to what the DNA reads."""

    recommendation_id: str
    outcome_id: str
    direction: str
    outcome: str
    success: bool
    timeframe: str | None
    session_bucket: str | None
    confidence_stated: float | None
    r_multiple: float | None
    mae_r: float | None
    mfe_r: float | None
    created_at: datetime | None
    closed_at: datetime | None

    @property
    def holding_hours(self) -> float | None:
        if self.created_at is None or self.closed_at is None:
            return None
        seconds = (self.closed_at - self.created_at).total_seconds()
        return seconds / 3600 if seconds >= 0 else None


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One trade the user reported taking. Behaviour, never accuracy (D4)."""

    trade_id: str
    recommendation_id: str | None
    r_multiple: float | None


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    plans: tuple[PlanRecord, ...] = ()
    trades: tuple[TradeRecord, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.plans and not self.trades
