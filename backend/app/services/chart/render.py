"""Render the chart the agent looks at — from the candles the engines read.

The agent analyses gold visually as well as numerically, so it needs a picture.
There are two ways to produce one, and the choice matters more than it looks.

AiChart screenshots the live web chart with a headless browser, and its own
comment names the resulting problem: *"The MCP agent has always looked at real
charts while the platform's engine read a JSON summary of the same market. Two
ways of seeing produce two answers."* A screenshot shows whatever the chart
happened to be displaying — a different window, a different last candle, an
indicator the engines never computed.

So Leovee draws the image **from the same candle rows the engines were given**.
One truth, two presentations. It also removes a browser, a JS runtime and a
running frontend from the analysis path: a decision no longer fails because a
web page did not load, and rendering three timeframes costs milliseconds rather
than seconds.

The drawing is deliberately plain — candles, the levels and zones the engines
found, and axes. It is evidence for a model to read, not a product surface, and
decoration would only compete with the structure it is meant to show.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw

from app.engines.bar import OHLCBar

__all__ = ["ChartTheme", "ChartImage", "render_chart_png", "render_chart_base64"]


@dataclass(frozen=True, slots=True)
class ChartTheme:
    width: int = 1280
    height: int = 720
    padding_left: int = 12
    padding_right: int = 96
    padding_top: int = 36
    padding_bottom: int = 28
    background: tuple[int, int, int] = (14, 17, 23)
    grid: tuple[int, int, int] = (34, 40, 49)
    text: tuple[int, int, int] = (200, 208, 218)
    bullish: tuple[int, int, int] = (34, 197, 94)
    bearish: tuple[int, int, int] = (239, 68, 68)
    support: tuple[int, int, int] = (56, 189, 248)
    resistance: tuple[int, int, int] = (250, 204, 21)
    demand: tuple[int, int, int, int] = (34, 197, 94, 48)
    supply: tuple[int, int, int, int] = (239, 68, 68, 48)


@dataclass(slots=True)
class ChartImage:
    png: bytes
    width: int
    height: int
    #: What the picture actually shows, so a caption can state it rather than
    #: leaving the model to infer the window from pixels.
    symbol: str
    timeframe: str
    bar_count: int
    price_low: float
    price_high: float
    drawn: list[str] = field(default_factory=list)

    def to_base64(self) -> str:
        return base64.b64encode(self.png).decode("ascii")


def render_chart_png(
    bars: list[OHLCBar],
    *,
    symbol: str,
    timeframe: str,
    structure: dict[str, Any] | None = None,
    zones: dict[str, Any] | None = None,
    theme: ChartTheme | None = None,
    max_bars: int = 180,
) -> ChartImage:
    """Draw candles plus whatever structure the engines found.

    `max_bars` bounds the window because a legible candle needs a few pixels:
    a thousand bars in 1280 pixels is a smear, and a model reading a smear will
    confidently describe structure that is not there.
    """
    if not bars:
        raise ValueError("cannot render a chart with no candles")

    style = theme or ChartTheme()
    window = bars[-max_bars:]

    lows = [bar.low for bar in window]
    highs = [bar.high for bar in window]
    price_low = min(lows)
    price_high = max(highs)

    # Include any level being drawn in the vertical range, or a support just
    # below the window would be clipped off the image exactly when it matters.
    extra: list[float] = []
    if structure:
        extra += [
            float(value)
            for key in ("nearest_support", "nearest_resistance")
            if (value := structure.get(key)) is not None
        ]
    if zones:
        for zone in (zones.get("demand") or []) + (zones.get("supply") or []):
            extra += [float(zone["low"]), float(zone["high"])]
    if extra:
        price_low = min(price_low, *extra)
        price_high = max(price_high, *extra)

    span = price_high - price_low
    if span <= 0:
        # A perfectly flat window still has to render; give it a nominal range
        # so every candle does not collapse onto one pixel row.
        span = max(abs(price_high), 1.0) * 0.001
        price_low -= span / 2
        price_high += span / 2
    # Breathing room so candles do not touch the frame.
    pad = span * 0.05
    price_low -= pad
    price_high += pad
    span = price_high - price_low

    image = Image.new("RGB", (style.width, style.height), style.background)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    shade = ImageDraw.Draw(overlay)

    plot_left = style.padding_left
    plot_right = style.width - style.padding_right
    plot_top = style.padding_top
    plot_bottom = style.height - style.padding_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    def y_for(price: float) -> float:
        return plot_bottom - ((price - price_low) / span) * plot_height

    drawn: list[str] = []

    # Horizontal grid with prices on the right.
    for i in range(5):
        price = price_low + span * i / 4
        y = y_for(price)
        draw.line([(plot_left, y), (plot_right, y)], fill=style.grid, width=1)
        draw.text((plot_right + 6, y - 6), f"{price:,.2f}", fill=style.text)

    if zones:
        zone_fills: tuple[tuple[str, tuple[int, int, int, int]], ...] = (
            ("demand", style.demand),
            ("supply", style.supply),
        )
        for kind, zone_fill in zone_fills:
            for zone in zones.get(kind) or []:
                top = y_for(float(zone["high"]))
                bottom = y_for(float(zone["low"]))
                shade.rectangle([plot_left, top, plot_right, bottom], fill=zone_fill)
                drawn.append(f"{kind}_zone")

    if structure:
        level_styles: tuple[tuple[str, tuple[int, int, int], str], ...] = (
            ("nearest_support", style.support, "S"),
            ("nearest_resistance", style.resistance, "R"),
        )
        for key, line_colour, label in level_styles:
            value = structure.get(key)
            if value is None:
                continue
            y = y_for(float(value))
            draw.line([(plot_left, y), (plot_right, y)], fill=line_colour, width=1)
            draw.text((plot_left + 4, y - 12), f"{label} {float(value):,.2f}", fill=line_colour)
            drawn.append(key)

    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    slot = plot_width / max(1, len(window))
    body_width = max(1.0, slot * 0.6)
    for index, bar in enumerate(window):
        centre = plot_left + slot * (index + 0.5)
        candle_colour = style.bullish if bar.close >= bar.open else style.bearish
        draw.line(
            [(centre, y_for(bar.high)), (centre, y_for(bar.low))], fill=candle_colour, width=1
        )
        top = y_for(max(bar.open, bar.close))
        bottom = y_for(min(bar.open, bar.close))
        if bottom - top < 1:
            # A doji still needs to be visible as a bar rather than vanishing.
            bottom = top + 1
        draw.rectangle(
            [centre - body_width / 2, top, centre + body_width / 2, bottom],
            fill=candle_colour,
        )

    last = window[-1]
    draw.text(
        (style.padding_left, 10),
        f"{symbol}  {timeframe}   {len(window)} bars   last {last.close:,.2f}"
        f"   {window[0].ts:%Y-%m-%d %H:%M} → {last.ts:%Y-%m-%d %H:%M} UTC",
        fill=style.text,
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return ChartImage(
        png=buffer.getvalue(),
        width=style.width,
        height=style.height,
        symbol=symbol,
        timeframe=timeframe,
        bar_count=len(window),
        price_low=price_low,
        price_high=price_high,
        drawn=sorted(set(drawn)),
    )


def render_chart_base64(bars: list[OHLCBar], **kwargs: Any) -> str:
    return render_chart_png(bars, **kwargs).to_base64()
