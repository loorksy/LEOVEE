from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChartSemanticType(StrEnum):
    """What is being drawn — the renderer-neutral vocabulary (ADR 0004).

    This replaces six coarse buckets (``DRAW_ZONE``, ``DRAW_STRUCTURE``,
    ``DRAW_LIQUIDITY``, ``DRAW_SETUP``, ``DRAW_LEVEL``, ``LABEL``) with the
    twenty-four the reference implementation actually draws. The six were not a
    simplification — they were a lossy projection. A neckline, a channel and a
    supply zone all arrived as ``DRAW_STRUCTURE``, so the renderer had to guess
    which tool to use from the anchor count, and a chart drawn from a guess
    disagrees with the narrative that cites it.

    Named for **meaning**, never for a library primitive. ``neckline`` says what
    the line is; ``trend_line`` would not, and the moment the vocabulary names a
    drawing tool the renderer stops being replaceable.
    """

    PRICE_LINE = "price_line"
    TREND_LINE = "trend_line"
    FORECAST_PATH = "forecast_path"
    CHANNEL = "channel"
    PARALLEL_CHANNEL = "parallel_channel"
    REGRESSION_TREND = "regression_trend"
    ZONE = "zone"
    SUPPLY_ZONE = "supply_zone"
    DEMAND_ZONE = "demand_zone"
    DECISION_ZONE = "decision_zone"
    RANGE_BOX = "range_box"
    RETEST_ZONE = "retest_zone"
    FIB_RETRACEMENT = "fib_retracement"
    BASELINE = "baseline"
    MARKER = "marker"
    LABELED_ARROW = "labeled_arrow"
    BREAKOUT_ARROW = "breakout_arrow"
    HISTOGRAM_BAND = "histogram_band"
    POLYLINE_PATTERN = "polyline_pattern"
    PATTERN_LABEL = "pattern_label"
    NECKLINE = "neckline"
    RISK_REWARD_BOX = "risk_reward_box"
    LONG_POSITION = "long_position"
    SHORT_POSITION = "short_position"


class ChartSemanticRole(StrEnum):
    """Why it is being drawn.

    Orthogonal to the type on purpose. A horizontal line is a `price_line`
    whether it marks a stop or a target, and collapsing the two axes is how a
    renderer ends up styling take-profits like stop-losses — the shape was never
    the thing that differed.
    """

    SUPPORT = "support"
    RESISTANCE = "resistance"
    DEMAND_ZONE = "demand_zone"
    SUPPLY_ZONE = "supply_zone"
    RANGE = "range"
    TRENDLINE = "trendline"
    CHANNEL = "channel"
    NECKLINE = "neckline"
    BREAKOUT = "breakout"
    RETEST = "retest"
    ENTRY = "entry"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    RISK_REWARD = "risk_reward"
    PATTERN = "pattern"
    FORECAST = "forecast"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    DECISION_ZONE = "decision_zone"


#: MT5's twenty-seven native drawing types are deliberately **not** here (D3).
#: The reference carried them so one pipeline could render to a terminal Leovee
#: does not connect to; keeping the vocabulary would leave a hole shaped exactly
#: like broker integration for someone to fill in later.


class ChartAnnotationLifecycle(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ChartAnchor(BaseModel):
    ts: str = Field(description="ISO-8601 timestamp")
    price: float
    timeframe: str | None = None


#: Bounds on a semantic model, so a single request cannot carry an arbitrarily
#: large graph to parse and validate. Both sit far above any real chart: the
#: geometry engine caps a snapshot at three patterns and a handful of lines.
MAX_ANCHORS_PER_OP = 64
MAX_OPS_PER_MODEL = 256


class ChartGeometry(BaseModel):
    anchors: list[ChartAnchor] = Field(min_length=1, max_length=MAX_ANCHORS_PER_OP)
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
    #: `solid` or `dashed`. Carries the one visual distinction that is *semantic*
    #: rather than cosmetic: a forming pattern is drawn dashed because it has not
    #: happened yet, and rendering it solid asserts a structure that does not
    #: exist.
    line_style: str | None = None


class ChartSemanticOperation(BaseModel):
    semantic_type: ChartSemanticType
    geometry: ChartGeometry
    style: ChartStyle = Field(default_factory=ChartStyle)
    #: Why this is drawn. Optional so an operation can be purely decorative,
    #: required in practice for anything the narrative cites.
    role: ChartSemanticRole | None = None
    #: The pattern this belongs to, from the geometry engine's own vocabulary.
    #: A string rather than a second enum: `PatternType` already exists in
    #: `app/engines/geometry/types.py`, and a copy here would be one more pair
    #: of lists to keep in step — which is exactly how the last vocabulary
    #: drifted.
    pattern_type: str | None = None
    #: 0-100, carried from the detector. A drawing with no confidence is
    #: indistinguishable on the chart from one the engine was certain about.
    confidence: int | None = None


class ChartSemanticModel(BaseModel):
    version: int = 1
    symbol: str | None = None
    timeframe: str | None = None
    operations: list[ChartSemanticOperation] = Field(
        default_factory=list, max_length=MAX_OPS_PER_MODEL
    )


class ChartAnnotationCreate(BaseModel):
    semantic_type: str = Field(min_length=1, max_length=64)
    geometry_json: dict[str, Any]
    style_json: dict[str, Any] = Field(default_factory=dict)
    analysis_id: str | None = None
    recommendation_id: str | None = None
    thesis_id: str | None = None
