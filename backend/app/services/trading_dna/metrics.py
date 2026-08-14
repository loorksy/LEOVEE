"""Ten measurements, each with a gate it has to clear before it may speak.

**A metric is supported or it is insufficient. There is no default value.** The
gates differ per metric because the questions differ: an average R stabilises
faster than a preference distribution, which needs enough samples for a share to
mean anything at all. Using one gate for everything would either silence the
cheap metrics or let the expensive ones report noise.

**Every supported number carries the rows it came from.** A profile is an
argument about the reader; asking them to take it on faith is the least
appropriate place to do that.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from app.services.trading_dna.types import (
    DnaMetric,
    EvidenceBundle,
    EvidenceReferences,
    EvidenceStatus,
    MetricKey,
    PlanRecord,
)

__all__ = ["MINIMUM_SAMPLES", "compute_metrics"]

#: Per-metric sample floors.
#:
#: A mean of R multiples settles quickly; a *share* of anything needs more,
#: because with five observations the largest bucket is 40% by accident. The
#: distribution metrics therefore sit higher than the scalar ones.
MINIMUM_SAMPLES: dict[MetricKey, int] = {
    MetricKey.AVERAGE_R: 5,
    MetricKey.WIN_LOSS_RATIO: 10,
    MetricKey.TIME_TO_TERMINAL: 5,
    MetricKey.MAE_R: 5,
    MetricKey.MFE_R: 5,
    MetricKey.CONFIDENCE_CALIBRATION: 10,
    MetricKey.DIRECTION_BIAS: 10,
    MetricKey.SESSION_PREFERENCE: 15,
    MetricKey.TIMEFRAME_PREFERENCE: 15,
    MetricKey.FOLLOW_THROUGH: 10,
}

_PRECISION = 4


def _insufficient(key: MetricKey, sample_size: int) -> DnaMetric:
    return DnaMetric(
        key=key,
        status=EvidenceStatus.INSUFFICIENT,
        value=None,
        sample_size=sample_size,
        required_sample=MINIMUM_SAMPLES[key],
    )


def _refs(plans: Sequence[PlanRecord]) -> EvidenceReferences:
    return EvidenceReferences(
        recommendation_ids=tuple(plan.recommendation_id for plan in plans),
        outcome_ids=tuple(plan.outcome_id for plan in plans),
    )


def _scalar(
    key: MetricKey,
    plans: Sequence[PlanRecord],
    values: Sequence[float],
) -> DnaMetric:
    if len(values) < MINIMUM_SAMPLES[key]:
        return _insufficient(key, len(values))
    return DnaMetric(
        key=key,
        status=EvidenceStatus.SUPPORTED,
        value=round(sum(values) / len(values), _PRECISION),
        sample_size=len(values),
        required_sample=MINIMUM_SAMPLES[key],
        references=_refs(plans),
    )


def _distribution(
    key: MetricKey,
    plans: Sequence[PlanRecord],
    labels: Sequence[str],
) -> DnaMetric:
    """A share per label, and the dominant share as the value.

    The value is the *largest* share rather than an index, because the question
    the reader asks is "am I concentrated?", and a single number they can compare
    against a gate answers it while a Herfindahl index does not.
    """
    if len(labels) < MINIMUM_SAMPLES[key]:
        return _insufficient(key, len(labels))
    counts = Counter(labels)
    total = len(labels)
    breakdown = {
        label: round(count / total, _PRECISION)
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }
    return DnaMetric(
        key=key,
        status=EvidenceStatus.SUPPORTED,
        value=max(breakdown.values()),
        breakdown=breakdown,
        sample_size=total,
        required_sample=MINIMUM_SAMPLES[key],
        references=_refs(plans),
    )


def compute_metrics(bundle: EvidenceBundle) -> list[DnaMetric]:
    """Every metric, in a fixed order, supported or explicitly not."""
    plans = list(bundle.plans)

    with_r = [plan for plan in plans if plan.r_multiple is not None]
    with_mae = [plan for plan in plans if plan.mae_r is not None]
    with_mfe = [plan for plan in plans if plan.mfe_r is not None]
    with_hold = [plan for plan in plans if plan.holding_hours is not None]
    with_conf = [plan for plan in plans if plan.confidence_stated is not None]
    with_tf = [plan for plan in plans if plan.timeframe]
    with_session = [plan for plan in plans if plan.session_bucket]
    directional = [plan for plan in plans if plan.direction in ("BUY", "SELL")]

    metrics = [
        _scalar(MetricKey.AVERAGE_R, with_r, [p.r_multiple or 0.0 for p in with_r]),
        _win_loss(plans),
        _scalar(MetricKey.TIME_TO_TERMINAL, with_hold, [p.holding_hours or 0.0 for p in with_hold]),
        _scalar(MetricKey.MAE_R, with_mae, [p.mae_r or 0.0 for p in with_mae]),
        _scalar(MetricKey.MFE_R, with_mfe, [p.mfe_r or 0.0 for p in with_mfe]),
        _calibration(with_conf),
        _distribution(MetricKey.DIRECTION_BIAS, directional, [p.direction for p in directional]),
        _distribution(
            MetricKey.SESSION_PREFERENCE,
            with_session,
            [p.session_bucket or "" for p in with_session],
        ),
        _distribution(
            MetricKey.TIMEFRAME_PREFERENCE, with_tf, [p.timeframe or "" for p in with_tf]
        ),
        _follow_through(bundle),
    ]
    return metrics


def _win_loss(plans: Sequence[PlanRecord]) -> DnaMetric:
    """Wins over losses. `None` when there are no losses yet.

    Not infinity, and not the win count: a ratio with an empty denominator is
    undefined, and substituting a large number would let a run of early wins
    read as an established edge.
    """
    key = MetricKey.WIN_LOSS_RATIO
    if len(plans) < MINIMUM_SAMPLES[key]:
        return _insufficient(key, len(plans))
    wins = sum(1 for plan in plans if plan.success)
    losses = len(plans) - wins
    if losses == 0:
        return _insufficient(key, len(plans))
    return DnaMetric(
        key=key,
        status=EvidenceStatus.SUPPORTED,
        value=round(wins / losses, _PRECISION),
        breakdown={"wins": float(wins), "losses": float(losses)},
        sample_size=len(plans),
        required_sample=MINIMUM_SAMPLES[key],
        references=_refs(plans),
    )


def _calibration(plans: Sequence[PlanRecord]) -> DnaMetric:
    """Mean absolute error between stated confidence and what happened.

    Zero is perfect. The sign is deliberately discarded: a reader who is
    overconfident on losers and underconfident on winners has a calibration
    problem in both directions, and a signed average would cancel it to nothing.
    """
    key = MetricKey.CONFIDENCE_CALIBRATION
    if len(plans) < MINIMUM_SAMPLES[key]:
        return _insufficient(key, len(plans))
    errors = [
        abs((plan.confidence_stated or 0.0) - (1.0 if plan.success else 0.0)) for plan in plans
    ]
    return DnaMetric(
        key=key,
        status=EvidenceStatus.SUPPORTED,
        value=round(sum(errors) / len(errors), _PRECISION),
        sample_size=len(plans),
        required_sample=MINIMUM_SAMPLES[key],
        references=_refs(plans),
    )


def _follow_through(bundle: EvidenceBundle) -> DnaMetric:
    """What share of published plans the reader actually reported taking.

    The one metric where a *trade* is the evidence rather than a distortion (D4).
    It measures the reader, not the analysis: a low figure with a good win rate
    means the plans were sound and went untaken, which is a different problem
    from plans that were taken and failed — and the two are indistinguishable
    without this.
    """
    key = MetricKey.FOLLOW_THROUGH
    plans = list(bundle.plans)
    if len(plans) < MINIMUM_SAMPLES[key]:
        return _insufficient(key, len(plans))
    taken = {trade.recommendation_id for trade in bundle.trades if trade.recommendation_id}
    followed = sum(1 for plan in plans if plan.recommendation_id in taken)
    return DnaMetric(
        key=key,
        status=EvidenceStatus.SUPPORTED,
        value=round(followed / len(plans), _PRECISION),
        breakdown={"followed": float(followed), "published": float(len(plans))},
        sample_size=len(plans),
        required_sample=MINIMUM_SAMPLES[key],
        references=EvidenceReferences(
            recommendation_ids=tuple(plan.recommendation_id for plan in plans),
            trade_ids=tuple(trade.trade_id for trade in bundle.trades),
        ),
    )
