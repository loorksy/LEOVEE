"""The charts the agent looks at, alongside the numbers it reads.

AiChart's own note on why this exists: *"The MCP agent has always looked at real
charts while the platform's engine read a JSON summary of the same market. Two
ways of seeing produce two answers."* The fix is not to remove one of the two —
a picture carries structure that a JSON summary flattens, and a model reading
both catches things either alone would miss. The fix is to make sure both views
come from the same candles, which is what `render.py` guarantees.

**Which frames.** The frame being analysed plus the two above it: enough to see
where an entry sits inside the structure that governs it, without spending the
budget on charts nobody will weigh. For a scalp on M1 that is M1/M5/M15; on M15
it is M15/H1/H4 — the decision frame plus its context ladder (ADR 0008).

**Best-effort by contract.** A missing frame degrades the read and is *reported*
as missing rather than quietly omitted. A model told "I could not show you H1"
reasons differently from one silently handed two charts instead of three, and
the difference matters when the missing frame is the one that would have
disagreed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeframes import ANALYSIS_WINDOW_BARS, MIN_CANDLES_FOR_ANALYSIS
from app.engines.bar import bars_from_candles
from app.models.enums import Timeframe
from app.services import market_data
from app.services.chart.render import ChartImage, render_chart_png

logger = structlog.get_logger(__name__)

__all__ = ["VisualSnapshot", "VisualEvidence", "visual_timeframes_for", "collect_visual_evidence"]

#: Decision frame -> the ladder shown with it. Values are the frame itself plus
#: the two above, so the agent always sees its entry in context.
_VISUAL_LADDER: dict[Timeframe, tuple[Timeframe, ...]] = {
    Timeframe.M1: (Timeframe.M1, Timeframe.M5, Timeframe.M15),
    Timeframe.M5: (Timeframe.M5, Timeframe.M15, Timeframe.H1),
    Timeframe.M15: (Timeframe.M15, Timeframe.H1, Timeframe.H4),
}

#: Bars per chart. Fewer than the analysis window: a legible candle needs a few
#: pixels, and a model reading a smear will confidently describe structure that
#: is not there.
VISUAL_BARS = 180


@dataclass(slots=True)
class VisualSnapshot:
    timeframe: str
    image: ChartImage

    def as_payload(self) -> dict[str, Any]:
        """Shape for a vision-capable model, with the caption stating the window."""
        return {
            "timeframe": self.timeframe,
            "media_type": "image/png",
            "data": self.image.to_base64(),
            "caption": (
                f"{self.image.symbol} {self.timeframe}: {self.image.bar_count} candles, "
                f"range {self.image.price_low:,.2f}–{self.image.price_high:,.2f}"
                + (f", drawn: {', '.join(self.image.drawn)}" if self.image.drawn else "")
            ),
        }


@dataclass(slots=True)
class VisualEvidence:
    snapshots: list[VisualSnapshot] = field(default_factory=list)
    #: Frames asked for and not obtained, each with a cause. Reported, never
    #: implied away.
    missing: list[dict[str, str]] = field(default_factory=list)
    elapsed_ms: int = 0

    def as_payload(self) -> dict[str, Any]:
        return {
            "snapshots": [snapshot.as_payload() for snapshot in self.snapshots],
            "missing": self.missing,
            "elapsed_ms": self.elapsed_ms,
        }


def visual_timeframes_for(timeframe: Timeframe | str) -> tuple[Timeframe, ...]:
    resolved = Timeframe(timeframe)
    # A frame outside the scalping range should not reach here, but falling
    # back to the M15 ladder is better than showing nothing at all.
    return _VISUAL_LADDER.get(resolved, _VISUAL_LADDER[Timeframe.M15])


async def collect_visual_evidence(
    session: AsyncSession,
    *,
    symbol: str,
    timeframe: Timeframe,
    structure: dict[str, Any] | None = None,
    zones: dict[str, Any] | None = None,
    bars_per_chart: int = VISUAL_BARS,
) -> VisualEvidence:
    """Render the ladder for one analysis. Never raises.

    An outright failure returns empty evidence and the decision proceeds on
    numbers alone, exactly as it did before this existed — losing the pictures
    must not lose the analysis.
    """
    started = time.monotonic()
    evidence = VisualEvidence()

    for frame in visual_timeframes_for(timeframe):
        try:
            symbol_row = await market_data.get_or_create_symbol(session, symbol)
            candles = await market_data.load_recent_candles(
                session,
                symbol_row.id,
                timeframe=frame,
                count=ANALYSIS_WINDOW_BARS,
            )
            bars = bars_from_candles(candles)
            if len(bars) < MIN_CANDLES_FOR_ANALYSIS:
                evidence.missing.append(
                    {
                        "timeframe": frame.value,
                        "reason": f"only {len(bars)} candles stored",
                    }
                )
                continue

            # Overlays belong to the analysed frame alone: the structure and
            # zones were computed there, and painting them onto H4 would show
            # the model levels that frame never produced.
            overlay_structure = structure if frame is timeframe else None
            overlay_zones = zones if frame is timeframe else None

            image = render_chart_png(
                bars,
                symbol=symbol,
                timeframe=frame.value,
                structure=overlay_structure,
                zones=overlay_zones,
                max_bars=bars_per_chart,
            )
            evidence.snapshots.append(VisualSnapshot(timeframe=frame.value, image=image))
        except Exception as exc:  # noqa: BLE001 — a lost picture must not lose the analysis
            logger.warning("visual_capture_failed", timeframe=frame.value, error=str(exc))
            evidence.missing.append({"timeframe": frame.value, "reason": type(exc).__name__})

    evidence.elapsed_ms = int((time.monotonic() - started) * 1000)
    return evidence
