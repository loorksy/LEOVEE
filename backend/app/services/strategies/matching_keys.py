"""Reducing a live moment to the bucket its statistics are stored under.

Every number the learning loop reports is an average within a bucket, so the
bucket key is the most consequential function in the package: get it wrong on
the read side and a strategy with a hundred outcomes reports as having none.

**Nothing wrote these keys.** `strategy_stats` has carried five bucket columns
since the schema was laid down, and the terminal hook read them from top-level
keys of `evidence_json` that no writer ever set. Every outcome therefore filed
under the constant tuple `DEFAULT/ANY/ANY/ANY/ANY` — one bucket per workspace,
containing everything. The columns existed; the classification did not.

**`UNKNOWN` and `ANY` are different words on purpose.** `UNKNOWN` means the
dimension could not be derived from this analysis — a fact about the data.
`ANY` is a wildcard used only when *reading*, to say "aggregate across this
dimension deliberately". Spelling them the same is how a missing measurement
becomes an intentional aggregate: the row looks like a considered decision to
ignore the session, when in truth nobody knew what the session was.

**The symbol is not part of the key** (D10). Gold is the only instrument, so a
symbol column here would be a constant carried through every query and every
index — and, worse, a hook for someone to later "generalise" the platform by
filling it in rather than by making a decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "UNKNOWN",
    "ANY",
    "SessionBucket",
    "VolatilityBucket",
    "RegimeBucket",
    "Classification",
    "session_bucket_at",
    "volatility_bucket_for",
    "regime_bucket_for",
    "classify",
    "classification_from_evidence",
    "read_ladder",
]

#: Could not be derived. A fact about this analysis.
UNKNOWN = "UNKNOWN"
#: Deliberately aggregated over. Only ever used on a read.
ANY = "ANY"


class SessionBucket:
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP = "OVERLAP"


class VolatilityBucket:
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class RegimeBucket:
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    ILLIQUID = "ILLIQUID"


#: Where the ATR sits relative to the instrument's own recent typical ATR.
#: A ratio, not an absolute: gold's "normal" moves, and a fixed threshold in
#: dollars would reclassify the whole market every time it did.
_VOLATILITY_LOW = 0.75
_VOLATILITY_HIGH = 1.5

#: London 07:00–16:00 UTC, New York 12:00–21:00 UTC; the four hours they share
#: are their own bucket because that is when gold actually moves, and averaging
#: it into either neighbour describes a market that does not exist.
_LONDON_HOURS = range(7, 16)
_NEW_YORK_HOURS = range(12, 21)


@dataclass(frozen=True, slots=True)
class Classification:
    """The five columns `strategy_stats` is keyed on, derived rather than defaulted."""

    strategy_code: str
    setup_type: str
    regime_bucket: str
    session_bucket: str
    volatility_bucket: str

    def to_dict(self) -> dict[str, str]:
        return {
            "strategy_code": self.strategy_code,
            "setup_type": self.setup_type,
            "regime_bucket": self.regime_bucket,
            "session_bucket": self.session_bucket,
            "volatility_bucket": self.volatility_bucket,
        }

    @property
    def derived(self) -> bool:
        """False when nothing could be classified — the old all-ANY state."""
        return any(
            value != UNKNOWN
            for value in (self.setup_type, self.regime_bucket, self.volatility_bucket)
        )


def session_bucket_at(moment: datetime) -> str:
    """Which trading session a UTC instant falls in.

    Clock arithmetic only — no spread table, no cost multiplier (ADR 0010). The
    session is a fact about liquidity and participation, and it belongs in the
    key because the same setup genuinely behaves differently at 03:00 and 14:00.
    """
    hour = moment.astimezone(UTC).hour
    in_london = hour in _LONDON_HOURS
    in_new_york = hour in _NEW_YORK_HOURS
    if in_london and in_new_york:
        return SessionBucket.OVERLAP
    if in_london:
        return SessionBucket.LONDON
    if in_new_york:
        return SessionBucket.NEW_YORK
    return SessionBucket.ASIA


def volatility_bucket_for(atr: float | None, *, typical_atr: float | None) -> str:
    """Loud, normal or quiet — relative to this instrument's own recent behaviour."""
    if not atr or not typical_atr or typical_atr <= 0:
        return UNKNOWN
    ratio = atr / typical_atr
    if ratio < _VOLATILITY_LOW:
        return VolatilityBucket.LOW
    if ratio > _VOLATILITY_HIGH:
        return VolatilityBucket.HIGH
    return VolatilityBucket.NORMAL


def regime_bucket_for(intelligence: dict[str, Any] | None) -> str:
    """The market-intelligence engine's own classification, upper-cased.

    Read from the engine rather than recomputed. A second regime classifier
    would disagree with the first somewhere, and the two answers would sit in
    the same payload with nothing to say which one the statistics used.
    """
    if not isinstance(intelligence, dict):
        return UNKNOWN
    regime = intelligence.get("regime")
    if not isinstance(regime, str) or not regime:
        return UNKNOWN
    return regime.upper()


def _setup_type_for(geometry: dict[str, Any] | None, structure: dict[str, Any] | None) -> str:
    """What kind of setup this is: the founding pattern, or failing that the shape.

    A pattern is the more specific answer and wins when there is one. Falling
    back to the structural shape keeps the dimension usable on the many gold
    scalps that have no named pattern at all — without it, every such plan would
    file under UNKNOWN and the bucket would be as useless as the constant it
    replaced.
    """
    if isinstance(geometry, dict):
        patterns = geometry.get("patterns")
        if isinstance(patterns, list) and patterns:
            leading = patterns[0]
            if isinstance(leading, dict):
                pattern_type = leading.get("pattern_type")
                if isinstance(pattern_type, str) and pattern_type:
                    return pattern_type.upper()
    if isinstance(structure, dict):
        shape = structure.get("shape")
        if isinstance(shape, str) and shape and shape != "unknown":
            return f"STRUCTURE_{shape.upper()}"
    return UNKNOWN


def _strategy_code_for(*, setup_type: str, regime_bucket: str, timeframe: str | None) -> str:
    """The strategy this plan belongs to.

    Under D7 a "strategy" is not a backtested specification — there is no engine
    to validate one against. It is the *vocabulary* the outcomes are grouped by:
    what kind of setup, in what regime, on what frame. Three plans sharing all
    three are the same idea being tried again, which is exactly the grouping a
    win rate needs to mean anything.
    """
    frame = (timeframe or UNKNOWN).upper()
    return f"{setup_type}_{regime_bucket}_{frame}".lower()


def classify(
    engines: dict[str, Any],
    *,
    timeframe: str | None,
    moment: datetime,
    typical_atr: float | None = None,
) -> Classification:
    """Derive all five keys from the engine bundle this analysis actually produced."""
    volatility = engines.get("volatility") if isinstance(engines.get("volatility"), dict) else {}
    intelligence = (
        engines.get("market_intelligence")
        if isinstance(engines.get("market_intelligence"), dict)
        else {}
    )
    geometry = engines.get("geometry") if isinstance(engines.get("geometry"), dict) else {}
    structure = engines.get("structure") if isinstance(engines.get("structure"), dict) else {}

    atr = volatility.get("atr") if isinstance(volatility, dict) else None
    setup_type = _setup_type_for(geometry, structure)
    regime_bucket = regime_bucket_for(intelligence)
    return Classification(
        strategy_code=_strategy_code_for(
            setup_type=setup_type, regime_bucket=regime_bucket, timeframe=timeframe
        ),
        setup_type=setup_type,
        regime_bucket=regime_bucket,
        session_bucket=session_bucket_at(moment),
        volatility_bucket=volatility_bucket_for(
            float(atr) if isinstance(atr, int | float) else None,
            typical_atr=typical_atr,
        ),
    )


def classification_from_evidence(evidence: dict[str, Any] | None) -> Classification:
    """Read back the classification a plan was filed under.

    One place knows the stored shape. The terminal hook used to read five
    separate top-level keys with five separate defaults, which is five chances
    for a writer and a reader to disagree silently — and they did: nothing wrote
    any of them.
    """
    stored = (evidence or {}).get("classification")
    if not isinstance(stored, dict):
        return Classification(UNKNOWN.lower(), UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN)

    def field(name: str, default: str = UNKNOWN) -> str:
        value = stored.get(name)
        return value if isinstance(value, str) and value else default

    return Classification(
        strategy_code=field("strategy_code", UNKNOWN.lower()),
        setup_type=field("setup_type"),
        regime_bucket=field("regime_bucket"),
        session_bucket=field("session_bucket"),
        volatility_bucket=field("volatility_bucket"),
    )


def read_ladder(classification: Classification) -> list[Classification]:
    """Progressively wider buckets to read statistics from, most specific first.

    A brand-new combination has no history, and reporting "no support" when the
    same setup has fifty outcomes in a slightly different session is a failure to
    look. Each rung widens exactly one dimension and says so by using `ANY`, so
    a caller that surfaces "38 outcomes, aggregated across sessions" is telling
    the truth about which number it read.

    Deliberately does not widen to nothing. The last rung still pins the setup
    and the regime; past that the average is over unrelated ideas and describes
    the workspace rather than the strategy.
    """
    exact = classification
    return [
        exact,
        Classification(
            exact.strategy_code, exact.setup_type, exact.regime_bucket, exact.session_bucket, ANY
        ),
        Classification(exact.strategy_code, exact.setup_type, exact.regime_bucket, ANY, ANY),
        Classification(exact.strategy_code, exact.setup_type, ANY, ANY, ANY),
    ]
