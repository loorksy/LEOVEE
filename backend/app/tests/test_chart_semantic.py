from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engines.chart_semantic import build_chart_semantic_model
from app.models.chart_annotation import ChartAnnotationStatus
from app.schemas.chart import ChartSemanticRole, ChartSemanticType
from app.services.chart_semantic_service import (
    ChartSemanticValidationError,
    validate_geometry,
    validate_semantic_model,
)


def test_validate_geometry_rejects_screen_pixels() -> None:
    with pytest.raises(ChartSemanticValidationError, match="screen"):
        validate_geometry(
            {
                "anchors": [{"ts": "2024-01-01T00:00:00+00:00", "price": 1.1}],
                "metadata": {"x": 10, "y": 20},
            }
        )


def test_validate_geometry_accepts_time_price_anchors() -> None:
    geom = validate_geometry(
        {
            "anchors": [
                {"ts": "2024-01-01T00:00:00+00:00", "price": 1.05},
                {"ts": "2024-01-02T00:00:00+00:00", "price": 1.10},
            ],
            "metadata": {"zone_type": "DEMAND"},
        }
    )
    assert len(geom.anchors) == 2


def test_semantic_model_lifecycle_fields_in_schema() -> None:
    model = validate_semantic_model(
        {
            "version": 1,
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "operations": [
                {
                    "semantic_type": ChartSemanticType.PRICE_LINE.value,
                    "geometry": {
                        "anchors": [{"ts": "2024-01-01T00:00:00+00:00", "price": 1.2}],
                    },
                }
            ],
        }
    )
    assert model.symbol == "XAUUSD"
    assert model.operations[0].semantic_type == ChartSemanticType.PRICE_LINE


def test_build_chart_semantic_model_from_engines() -> None:
    """Each engine output becomes the annotation that *names* what it is.

    Six coarse buckets used to stand in for twenty-four types, so a supply zone
    and a neckline both arrived as DRAW_STRUCTURE and the renderer had to guess
    the tool from the anchor count.
    """
    as_of = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    engines = {
        "zones": {
            "zones": [
                {"type": "DEMAND", "low": 2000.0, "high": 2004.0, "strength": 0.8},
                {"type": "SUPPLY", "low": 2020.0, "high": 2026.0, "strength": 0.6},
            ]
        },
        "liquidity": {"equal_highs": [{"price": 2030.0, "touches": 3}]},
    }
    decision = {
        "direction": "BUY",
        "levels": {"entry": 2005.0, "stop": 1998.0, "targets": [2018.0, 2030.0]},
    }
    model = build_chart_semantic_model(
        symbol="XAUUSD",
        timeframe="M15",
        as_of=as_of,
        engines=engines,
        decision=decision,
    )
    types = {op.semantic_type for op in model.operations}
    roles = {op.role for op in model.operations}

    assert ChartSemanticType.DEMAND_ZONE in types
    assert ChartSemanticType.SUPPLY_ZONE in types
    # Entry, stop and both targets are all horizontal lines — the *type* is the
    # same and the *role* is what differs, which is why the two axes are kept
    # apart: a renderer that styled take-profits like stop-losses would be
    # reading the only field that distinguishes them.
    assert types & {ChartSemanticType.PRICE_LINE}
    assert {
        ChartSemanticRole.ENTRY,
        ChartSemanticRole.STOP_LOSS,
        ChartSemanticRole.TAKE_PROFIT,
        ChartSemanticRole.LIQUIDITY_SWEEP,
    } <= roles


def test_a_degraded_decision_puts_no_plan_on_the_chart() -> None:
    """A NO_TRADE has no levels, and drawing the geometric placeholder would put
    a line at a price no published plan ever named."""
    model = build_chart_semantic_model(
        symbol="XAUUSD",
        timeframe="M15",
        as_of=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        engines={},
        decision={
            "direction": "NO_TRADE",
            "degraded": True,
            "degraded_reason": "LLM_UNAVAILABLE",
            "levels": None,
        },
    )
    assert model.operations == []


def test_a_zone_spans_its_own_time_range_when_the_engine_recorded_one() -> None:
    """Every anchor used to carry `as_of`, so a four-hour zone and a two-day
    structure both rendered as vertical pairs at the right edge."""
    as_of = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    model = build_chart_semantic_model(
        symbol="XAUUSD",
        timeframe="M15",
        as_of=as_of,
        engines={
            "zones": {
                "zones": [
                    {
                        "type": "DEMAND",
                        "low": 2000.0,
                        "high": 2004.0,
                        "from_ts": "2024-06-01T08:00:00+00:00",
                        "to_ts": "2024-06-01T11:00:00+00:00",
                    }
                ]
            }
        },
    )
    anchors = model.operations[0].geometry.anchors
    assert anchors[0].ts != anchors[1].ts
    assert anchors[0].ts.startswith("2024-06-01T08:00")


def test_annotation_status_enum_values() -> None:
    assert ChartAnnotationStatus.CREATED.value == "CREATED"
    assert ChartAnnotationStatus.ACTIVE.value == "ACTIVE"
    assert ChartAnnotationStatus.ARCHIVED.value == "ARCHIVED"
