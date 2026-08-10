from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChartSemanticType(StrEnum):
    DRAW_ZONE = "DRAW_ZONE"
    DRAW_STRUCTURE = "DRAW_STRUCTURE"
    DRAW_LIQUIDITY = "DRAW_LIQUIDITY"
    DRAW_SETUP = "DRAW_SETUP"
    DRAW_LEVEL = "DRAW_LEVEL"
    LABEL = "LABEL"


class ChartAnnotationLifecycle(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ChartAnchor(BaseModel):
    ts: str = Field(description="ISO-8601 timestamp")
    price: float
    timeframe: str | None = None


class ChartGeometry(BaseModel):
    anchors: list[ChartAnchor] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("anchors")
    @classmethod
    def anchors_time_price_only(cls, anchors: list[ChartAnchor]) -> list[ChartAnchor]:
        if not anchors:
            raise ValueError("anchors required")
        return anchors


class ChartStyle(BaseModel):
    color: str | None = None
    line_width: int | None = None
    fill_opacity: float | None = None
    label: str | None = None


class ChartSemanticOperation(BaseModel):
    semantic_type: ChartSemanticType
    geometry: ChartGeometry
    style: ChartStyle = Field(default_factory=ChartStyle)


class ChartSemanticModel(BaseModel):
    version: int = 1
    symbol: str | None = None
    timeframe: str | None = None
    operations: list[ChartSemanticOperation] = Field(default_factory=list)


class ChartAnnotationCreate(BaseModel):
    semantic_type: str = Field(min_length=1, max_length=64)
    geometry_json: dict[str, Any]
    style_json: dict[str, Any] = Field(default_factory=dict)
    analysis_id: str | None = None
    recommendation_id: str | None = None
    thesis_id: str | None = None
