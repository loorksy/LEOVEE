"""The typed contract every engine output crosses.

Frozen before the layers above are built, on purpose. Three of them read these
shapes — the agent stages (M6), the recommendation lifecycle (M7) and the chart
(M9) — and a contract fixed after its consumers exist is not a contract, it is a
description of whatever the consumers happened to accept.

Two rules hold everywhere below.

**Unavailable is a first-class answer.** Every engine may decline, and declining
carries a machine-readable reason plus the engine's own name. The alternative —
a payload of nulls and zeros — is indistinguishable from a market that is
genuinely flat, and that ambiguity is what let placeholders publish invented
evidence for as long as they did.

**A number is never published without its provenance.** Where a value could have
been measured or modelled, the model says which. A fallback returned as a
measurement is worse than no number: the reader has no way to discount it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EngineName",
    "UnavailableReason",
    "EngineUnavailable",
    "Bias",
    "RegimeName",
    "Stance",
    "VolatilityOutput",
    "StructureOutput",
    "GeometryOutput",
    "LiquidityOutput",
    "ZonesOutput",
    "ScenarioOutput",
    "MarketIntelligenceOutput",
    "MtfOutput",
    "RiskOutput",
    "PriceContextModel",
    "PlanSanityOutput",
    "EngineBundle",
    "parse_engine_output",
]

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Score100 = Annotated[int, Field(ge=0, le=100)]


class EngineName(StrEnum):
    VOLATILITY = "volatility"
    STRUCTURE = "structure"
    GEOMETRY = "geometry"
    LIQUIDITY = "liquidity"
    ZONES = "zones"
    SCENARIOS = "scenarios"
    MARKET_INTELLIGENCE = "market_intelligence"
    MTF = "mtf"
    RISK = "risk"
    PLAN_SANITY = "plan_sanity"


class UnavailableReason(StrEnum):
    #: Not ported yet — a migration gap a release closes.
    ENGINE_NOT_IMPLEMENTED = "ENGINE_NOT_IMPLEMENTED"
    #: Real engine, too little or malformed data — a feed condition that clears.
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Bias(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    #: Not "no bias" — *not readable*. A frame with nine bars has no structure
    #: to read, and reporting that as NEUTRAL turns a data fact into a market
    #: claim.
    UNKNOWN = "UNKNOWN"


class RegimeName(StrEnum):
    TRENDING = "trending"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"


class Stance(StrEnum):
    """How to build the plan. Never which way to trade."""

    TREND_FOLLOWING = "TREND_FOLLOWING"
    MEAN_REVERTING = "MEAN_REVERTING"
    DEFENSIVE = "DEFENSIVE"


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class EngineUnavailable(_Base):
    status: Literal["unavailable"]
    reason: UnavailableReason
    engine: str
    detail: str | None = None


class VolatilityOutput(_Base):
    atr: float | None = None
    regime: str | None = None


class StructureOutput(_Base):
    bias: Bias
    shape: Literal["uptrend", "downtrend", "range", "unknown"]
    current_price: float
    swing_high: float | None = None
    swing_low: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    supports: list[dict[str, Any]] = Field(default_factory=list)
    resistances: list[dict[str, Any]] = Field(default_factory=list)


class GeometryOutput(_Base):
    candle_count: int
    atr: float
    pivots: list[dict[str, Any]] = Field(default_factory=list)
    trendlines: list[dict[str, Any]] = Field(default_factory=list)
    channels: list[dict[str, Any]] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    candlesticks: list[dict[str, Any]] = Field(default_factory=list)


class LiquidityOutput(_Base):
    equal_highs: list[dict[str, Any]] = Field(default_factory=list)
    equal_lows: list[dict[str, Any]] = Field(default_factory=list)
    sweeps: list[dict[str, Any]] = Field(default_factory=list)


class ZonesOutput(_Base):
    zones: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioOutput(_Base):
    scenarios: list[dict[str, Any]] = Field(default_factory=list)


class MarketIntelligenceOutput(_Base):
    regime: RegimeName
    stance: Stance
    #: The DI lean, which exists whatever the regime.
    trend_direction: Literal["bullish", "bearish", "neutral"]
    #: The trend *claim*, which only a trending regime is allowed to make.
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: Confidence
    candle_count: int
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, bool] = Field(default_factory=dict)


class MtfRoles(BaseModel):
    """The three roles the constitution requires every answer to name."""

    model_config = ConfigDict(frozen=True)

    leads: str | None
    context: list[str]
    times_entry: str


class MtfOutput(_Base):
    stack: list[str]
    decision_timeframe: str
    biases: dict[str, Bias]
    alignment: Literal["FULL_BULLISH", "FULL_BEARISH", "MIXED_BULLISH", "MIXED_BEARISH", "NEUTRAL"]
    trade_bias: Bias
    #: A disagreement between the frame being traded and the frame that leads.
    #: Reported, never averaged away.
    conflict: bool
    roles: MtfRoles
    frames: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RiskOutput(_Base):
    """Position risk from the plan's own levels.

    Untyped until now, which is how it kept a `spread_cost` field describing a
    thirty-pip constant nobody had measured (ADR 0010) with nothing to notice.
    The direction is *read off the levels* rather than passed in, so a stop above
    entry is a short rather than an invalid plan.
    """

    approved: bool
    decision: Literal["TRADE", "NO_TRADE"]
    reason: str | None = None
    direction: Literal["BUY", "SELL"] | None = None
    position_size_units: float | None = None
    risk_distance: float | None = None
    risk_pips: float | None = None
    #: None rather than a negative number when a target sits on the stop's side:
    #: a negative ratio downstream reads as a very confident bad trade.
    reward_risk: float | None = None
    pip_size: float | None = None


class PriceContextModel(BaseModel):
    """What the candles say about how this market moves right now.

    This replaced a `SpreadEstimateModel` carrying pips, a trading session and a
    `source: "observed" | "static_model"` provenance flag — the typed face of a
    cost model that no longer exists (ADR 0010). Nothing here is estimated:
    `noise` is the median wick measured off the bars, `atr` is measured
    volatility, and `observed_spread` is present only when a live quote was
    supplied and gates nothing.
    """

    model_config = ConfigDict(frozen=True)

    #: Median wick per bar — the part of the range price gave back.
    noise: float
    atr: float
    last_close: float
    bars: int
    #: A live quote when there was one. Never modelled, never a gate.
    observed_spread: float | None = None


class PlanSanityOutput(_Base):
    viable: bool
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    context: PriceContextModel
    stop_distance: float
    stop_distance_pips: float
    #: How many times the plan's stop covers the measured wick noise.
    stop_noise_multiple: float | None = None
    required_stop_distance: float | None = None
    #: The first target's distance in ATR.
    first_target_atr: float | None = None
    reward_risk: float | None = None


#: Which model validates which engine's payload.
_OUTPUT_MODELS: dict[EngineName, type[_Base]] = {
    EngineName.VOLATILITY: VolatilityOutput,
    EngineName.STRUCTURE: StructureOutput,
    EngineName.GEOMETRY: GeometryOutput,
    EngineName.LIQUIDITY: LiquidityOutput,
    EngineName.ZONES: ZonesOutput,
    EngineName.SCENARIOS: ScenarioOutput,
    EngineName.MARKET_INTELLIGENCE: MarketIntelligenceOutput,
    EngineName.MTF: MtfOutput,
    EngineName.RISK: RiskOutput,
    EngineName.PLAN_SANITY: PlanSanityOutput,
}

T = TypeVar("T", bound=_Base)


def parse_engine_output(engine: EngineName, payload: dict[str, Any]) -> _Base:
    """Validate a raw engine dict into its typed shape, or into a decline.

    The decline branch is checked first and by *shape*, not by engine: any
    engine may decline, and an unavailable payload must never be coerced into
    the success model — that is how a missing answer becomes a zeroed one.
    """
    if payload.get("status") == "unavailable":
        return EngineUnavailable.model_validate(payload)
    model = _OUTPUT_MODELS.get(engine)
    if model is None:
        raise KeyError(f"no output contract registered for engine {engine.value!r}")
    return model.model_validate(payload)


class EngineBundle(BaseModel):
    """Everything the orchestrator assembles before the decision is made."""

    model_config = ConfigDict(extra="allow", frozen=True)

    volatility: VolatilityOutput | EngineUnavailable
    structure: StructureOutput | EngineUnavailable
    geometry: GeometryOutput | EngineUnavailable
    liquidity: LiquidityOutput | EngineUnavailable
    zones: ZonesOutput | EngineUnavailable
    scenarios: ScenarioOutput | EngineUnavailable
    market_intelligence: MarketIntelligenceOutput | EngineUnavailable
    mtf: MtfOutput | EngineUnavailable
    # Both were missing, so the bundle described eight of the ten engines the
    # orchestrator actually assembles — and the two it omitted are the two
    # that carry the plan's own numbers.
    risk: RiskOutput | EngineUnavailable
    plan_sanity: PlanSanityOutput | EngineUnavailable
