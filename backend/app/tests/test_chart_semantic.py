from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engines.chart_semantic import build_chart_semantic_model
from app.models.chart_annotation import ChartAnnotationStatus
from app.schemas.chart import ChartSemanticType
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
                    "semantic_type": ChartSemanticType.DRAW_LEVEL.value,
                    "geometry": {
                        "anchors": [{"ts": "2024-01-01T00:00:00+00:00", "price": 1.2}],
                    },
                }
            ],
        }
    )
    assert model.symbol == "XAUUSD"
    assert model.operations[0].semantic_type == ChartSemanticType.DRAW_LEVEL


def test_build_chart_semantic_model_from_engines() -> None:
    as_of = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    engines = {
        "zones": {
            "zones": [{"type": "DEMAND", "low": 1.08, "high": 1.09}],
        },
        "structure": {"swing_low": 1.08, "swing_high": 1.12, "bias": "bullish", "label": "BOS"},
        "risk": {"entry": 1.10, "stop": 1.08},
        "decision": {"direction": "BUY"},
    }
    model = build_chart_semantic_model(
        symbol="XAUUSD",
        timeframe="H1",
        as_of=as_of,
        engines=engines,
    )
    types = {op.semantic_type for op in model.operations}
    assert ChartSemanticType.DRAW_ZONE in types
    assert ChartSemanticType.DRAW_STRUCTURE in types
    assert ChartSemanticType.DRAW_SETUP in types


def test_annotation_status_enum_values() -> None:
    assert ChartAnnotationStatus.CREATED.value == "CREATED"
    assert ChartAnnotationStatus.ACTIVE.value == "ACTIVE"
    assert ChartAnnotationStatus.ARCHIVED.value == "ARCHIVED"
