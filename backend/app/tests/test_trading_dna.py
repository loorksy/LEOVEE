"""What the profile may claim about the reader, and what it must refuse to.

A trading profile is an argument about a person, made by a machine, from a
sample the person did not choose. Most of these tests are about the refusals —
because a metric that always produces a number produces one from four
observations too, and presents it beside one built from four hundred with
nothing to tell them apart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.trading_dna import (
    DOMINANCE_GATE,
    MIN_PERSONA_SAMPLE,
    MINIMUM_SAMPLES,
    EvidenceBundle,
    EvidenceStatus,
    MetricKey,
    PersonaName,
    PlanRecord,
    TradeRecord,
    compute_metrics,
    derive_persona,
)

pytestmark = pytest.mark.no_db

EPOCH = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)


def _plan(
    index: int,
    *,
    success: bool = True,
    direction: str = "BUY",
    timeframe: str = "M15",
    session: str = "LONDON",
    confidence: float | None = 0.6,
    r: float | None = 1.0,
    mae: float | None = 0.4,
    mfe: float | None = 1.8,
    hours: float | None = 2.0,
) -> PlanRecord:
    closed = EPOCH + timedelta(hours=hours) if hours is not None else None
    return PlanRecord(
        recommendation_id=f"rec-{index}",
        outcome_id=f"out-{index}",
        direction=direction,
        outcome="TARGET_REACHED" if success else "INVALIDATED",
        success=success,
        timeframe=timeframe,
        session_bucket=session,
        confidence_stated=confidence,
        r_multiple=r,
        mae_r=mae,
        mfe_r=mfe,
        created_at=EPOCH,
        closed_at=closed,
    )


def _by_key(bundle: EvidenceBundle) -> dict[MetricKey, object]:
    return {metric.key: metric for metric in compute_metrics(bundle)}


def test_an_empty_record_produces_every_metric_as_insufficient() -> None:
    """Not an empty list, and not zeroes.

    A missing key reads as a bug and a zero reads as a measurement. "We have not
    seen enough of this yet" is the answer, and it has to be sayable.
    """
    metrics = compute_metrics(EvidenceBundle())
    assert len(metrics) == len(MetricKey)
    assert all(metric.status is EvidenceStatus.INSUFFICIENT for metric in metrics)
    assert all(metric.value is None for metric in metrics)
    # And each one says what it would have needed.
    assert all(metric.required_sample > 0 for metric in metrics)


def test_a_metric_one_sample_short_of_its_gate_stays_silent() -> None:
    need = MINIMUM_SAMPLES[MetricKey.AVERAGE_R]
    short = _by_key(EvidenceBundle(plans=tuple(_plan(i) for i in range(need - 1))))
    at_gate = _by_key(EvidenceBundle(plans=tuple(_plan(i) for i in range(need))))

    assert short[MetricKey.AVERAGE_R].status is EvidenceStatus.INSUFFICIENT  # type: ignore[attr-defined]
    assert at_gate[MetricKey.AVERAGE_R].status is EvidenceStatus.SUPPORTED  # type: ignore[attr-defined]


def test_distribution_metrics_have_higher_gates_than_scalar_ones() -> None:
    """With five observations the largest bucket is 40% by accident.

    One gate for everything would either silence the cheap metrics or let the
    expensive ones report noise.
    """
    assert MINIMUM_SAMPLES[MetricKey.SESSION_PREFERENCE] > MINIMUM_SAMPLES[MetricKey.AVERAGE_R]
    assert MINIMUM_SAMPLES[MetricKey.TIMEFRAME_PREFERENCE] > MINIMUM_SAMPLES[MetricKey.MAE_R]


def test_a_supported_metric_carries_the_rows_it_came_from() -> None:
    """A conclusion the reader cannot trace back is one they must take on faith."""
    bundle = EvidenceBundle(plans=tuple(_plan(i) for i in range(12)))
    metric = _by_key(bundle)[MetricKey.AVERAGE_R]
    assert metric.supported  # type: ignore[attr-defined]
    assert len(metric.references.recommendation_ids) == 12  # type: ignore[attr-defined]
    assert "rec-0" in metric.references.recommendation_ids  # type: ignore[attr-defined]


def test_an_unbeaten_record_reports_no_win_loss_ratio() -> None:
    """A ratio with an empty denominator is undefined.

    Substituting a large number would let a run of early wins read as an
    established edge — which is exactly when a reader is most inclined to
    believe it.
    """
    bundle = EvidenceBundle(plans=tuple(_plan(i, success=True) for i in range(20)))
    metric = _by_key(bundle)[MetricKey.WIN_LOSS_RATIO]
    assert metric.status is EvidenceStatus.INSUFFICIENT  # type: ignore[attr-defined]
    assert metric.value is None  # type: ignore[attr-defined]


def test_calibration_error_does_not_cancel_itself_out() -> None:
    """Overconfident on losers and underconfident on winners is two problems.

    A signed average would net them to zero and report perfect calibration.
    """
    plans = [
        *[_plan(i, success=False, confidence=0.9) for i in range(6)],
        *[_plan(10 + i, success=True, confidence=0.1) for i in range(6)],
    ]
    metric = _by_key(EvidenceBundle(plans=tuple(plans)))[MetricKey.CONFIDENCE_CALIBRATION]
    assert metric.supported  # type: ignore[attr-defined]
    assert metric.value == pytest.approx(0.9)  # type: ignore[attr-defined]


def test_direction_bias_reports_the_shares_and_the_dominant_one() -> None:
    plans = [
        *[_plan(i, direction="BUY") for i in range(15)],
        *[_plan(50 + i, direction="SELL") for i in range(5)],
    ]
    metric = _by_key(EvidenceBundle(plans=tuple(plans)))[MetricKey.DIRECTION_BIAS]
    assert metric.supported  # type: ignore[attr-defined]
    assert metric.breakdown == {"BUY": 0.75, "SELL": 0.25}  # type: ignore[attr-defined]
    assert metric.value == 0.75  # type: ignore[attr-defined]


def test_follow_through_separates_plans_ignored_from_plans_that_failed() -> None:
    """A low figure with a good win rate is a different problem entirely.

    Without this the two are indistinguishable: sound plans nobody took, and
    plans that were taken and lost, both show up as a record that did not work.
    """
    plans = tuple(_plan(i) for i in range(20))
    trades = tuple(TradeRecord(f"t-{i}", f"rec-{i}", 1.0) for i in range(5))
    metric = _by_key(EvidenceBundle(plans=plans, trades=trades))[MetricKey.FOLLOW_THROUGH]
    assert metric.supported  # type: ignore[attr-defined]
    assert metric.value == 0.25  # type: ignore[attr-defined]
    assert metric.breakdown == {"followed": 5.0, "published": 20.0}  # type: ignore[attr-defined]


def test_metrics_that_would_need_execution_data_do_not_exist() -> None:
    """Eight of the reference's eighteen, dropped rather than approximated.

    Each assumed a fill: spread and slippage variance, position sizing,
    break-even and trailing management. Approximating any of them produces a
    number that looks like behavioural insight and is an artefact of the
    platform's own shape.
    """
    keys = {key.value for key in MetricKey}
    for absent in (
        "execution_consistency",
        "risk_tolerance",
        "risk_scaling",
        "break_even_behavior",
        "trailing_behavior",
        "preferred_symbols",
        "portfolio_concentration",
        "backtest_coverage",
    ):
        assert absent not in keys, absent


# --- the persona --------------------------------------------------------------


def test_a_thin_record_is_unclassified_rather_than_stereotyped() -> None:
    """A persona from six plans is a label the platform then reasons with —
    and keeps reasoning with long after the evidence would say otherwise."""
    bundle = EvidenceBundle(plans=tuple(_plan(i) for i in range(MIN_PERSONA_SAMPLE - 1)))
    persona = derive_persona(bundle)
    assert persona.name is PersonaName.UNCLASSIFIED
    assert persona.reason == "PERSONA_INSUFFICIENT_SAMPLE"


def test_a_consistent_record_earns_its_name() -> None:
    bundle = EvidenceBundle(plans=tuple(_plan(i, hours=1.5) for i in range(20)))
    persona = derive_persona(bundle)
    assert persona.name is PersonaName.SCALPER
    assert persona.support == 1.0


def test_a_reader_who_trades_several_ways_is_not_given_one_name() -> None:
    """Naming the largest band anyway would be a label chosen by a plurality."""
    plans = [
        *[_plan(i, hours=1.0) for i in range(8)],
        *[_plan(20 + i, hours=10.0) for i in range(7)],
        *[_plan(40 + i, hours=40.0) for i in range(5)],
    ]
    persona = derive_persona(EvidenceBundle(plans=tuple(plans)))
    assert persona.name is PersonaName.UNCLASSIFIED
    assert persona.reason == "PERSONA_MIXED"
    assert persona.support is not None and persona.support < DOMINANCE_GATE


def test_plans_without_a_holding_time_do_not_count_toward_the_persona() -> None:
    """An unclosed plan has no duration, and counting it as zero would make
    every reader a scalper."""
    plans = tuple(_plan(i, hours=None) for i in range(30))
    persona = derive_persona(EvidenceBundle(plans=plans))
    assert persona.name is PersonaName.UNCLASSIFIED
    assert persona.sample_size == 0


def test_a_reader_holding_past_a_day_is_named_for_it() -> None:
    """The platform is scalp-only (D11), so this is a finding, not a category.

    Forcing them into `intraday` would hide that they are doing something the
    product did not intend.
    """
    bundle = EvidenceBundle(plans=tuple(_plan(i, hours=48.0) for i in range(15)))
    assert derive_persona(bundle).name is PersonaName.SWING
