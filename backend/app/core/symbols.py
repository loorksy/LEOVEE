"""The tradable universe: gold, and nothing else.

Leovee analyses **XAUUSD only** (owner decision, ADR 0007). The platform, the
agent, the engines, the memory and the learning loop are all built around one
instrument.

This is a product decision with real engineering consequences, and they mostly
run in the helpful direction. A single-instrument platform gets one set of
per-instrument tolerances instead of a table of them, one candle series to keep
warm, one stream subscription, and a memory in which every past episode is
directly comparable to the present one — a similar-case lookup does not have to
ask whether a EURUSD analogue means anything for gold.

The *mechanism* here stays general — an allowlist, a spec per instrument — while
its content is a single row. That costs nothing today and means adding silver
later is a one-line change rather than an excavation.

The allowlist is enforced at one chokepoint,
``app/services/market_data.py::resolve_symbol_code``. AiChart arrived at the same
discipline the hard way: its `LONORA_REFACTOR_LOG.md` records finding routes that
had quietly bypassed the check. Spreading the check across every route is how a
gap gets reintroduced.

**pip_location** follows OANDA's convention — the base-10 exponent at which one
pip sits, so a pip is ``10 ** pip_location``. Gold prices to two decimals, so it
is ``-2``, not the ``-4`` that most currency pairs use. Getting this wrong does
not fail loudly; it silently scales every stop distance, spread check and
position size by a factor of a hundred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AssetGroup",
    "InstrumentSpec",
    "GOLD",
    "INSTRUMENTS",
    "TRADABLE_SYMBOLS",
    "DEFAULT_SYMBOL",
    "normalize_symbol",
    "is_tradable",
    "instrument_for",
    "require_instrument",
    "pip_size",
    "UnknownSymbolError",
]


class AssetGroup(StrEnum):
    METAL = "metal"


class UnknownSymbolError(ValueError):
    """Raised when a symbol outside the allowlist reaches the data layer."""

    def __init__(self, raw: str) -> None:
        super().__init__(
            f"{raw!r} is not tradable on this platform. "
            f"Leovee analyses {', '.join(TRADABLE_SYMBOLS)} only."
        )
        self.raw = raw


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    symbol: str
    base: str
    quote: str
    group: AssetGroup
    #: Exponent at which one pip sits: pip = 10 ** pip_location.
    pip_location: int

    @property
    def oanda_instrument(self) -> str:
        return f"{self.base}_{self.quote}"

    @property
    def asset_class(self) -> str:
        return "METAL"


#: Gold against the US dollar — the platform's single instrument.
GOLD = InstrumentSpec(
    symbol="XAUUSD",
    base="XAU",
    quote="USD",
    group=AssetGroup.METAL,
    pip_location=-2,
)

INSTRUMENTS: tuple[InstrumentSpec, ...] = (GOLD,)

TRADABLE_SYMBOLS: tuple[str, ...] = tuple(spec.symbol for spec in INSTRUMENTS)

#: Used wherever a symbol is optional. With one instrument this is not really a
#: default so much as the answer, but keeping the indirection means the call
#: sites do not hard-code a ticker.
DEFAULT_SYMBOL: str = GOLD.symbol

_BY_SYMBOL: dict[str, InstrumentSpec] = {spec.symbol: spec for spec in INSTRUMENTS}
_SEPARATORS = re.compile(r"[\s/_\-.]+")


def normalize_symbol(raw: str) -> str:
    """Canonical spelling: uppercase, separators removed.

    Callers write ``XAU/USD``, ``xau_usd`` and ``XAU-USD`` for the same thing,
    and OANDA itself uses ``XAU_USD``. Normalising in one place keeps the
    allowlist from being defeated by punctuation.
    """
    return _SEPARATORS.sub("", raw).upper()


def is_tradable(raw: str) -> bool:
    return normalize_symbol(raw) in _BY_SYMBOL


def instrument_for(raw: str) -> InstrumentSpec | None:
    return _BY_SYMBOL.get(normalize_symbol(raw))


def require_instrument(raw: str) -> InstrumentSpec:
    """The allowlist gate. Raises rather than silently substituting gold."""
    spec = instrument_for(raw)
    if spec is None:
        raise UnknownSymbolError(raw)
    return spec


def pip_size(raw: str) -> float | None:
    """One pip, in price units. ``None`` when the symbol is not tradable."""
    spec = instrument_for(raw)
    return None if spec is None else 10.0**spec.pip_location
