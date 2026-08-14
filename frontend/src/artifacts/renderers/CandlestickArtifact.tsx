import { useEffect, useRef } from "react";
import type { ChatArtifact } from "../types";
import { chartPalette } from "./palette";

interface RawBar {
  t?: number | string;
  time?: number | string;
  o?: number;
  open?: number;
  h?: number;
  high?: number;
  l?: number;
  low?: number;
  c?: number;
  close?: number;
}

/** Normalise a candle payload into lightweight-charts' shape, accepting both
 *  the terse `{t,o,h,l,c}` and the spelled-out `{time,open,high,low,close}`. */
function toBars(content: string) {
  let raw: RawBar[] = [];
  try {
    const parsed = JSON.parse(content) as unknown;
    if (Array.isArray(parsed)) raw = parsed as RawBar[];
    else if (parsed && typeof parsed === "object") {
      const series = (parsed as { series?: unknown }).series;
      if (Array.isArray(series)) raw = series as RawBar[];
    }
  } catch {
    return [];
  }
  return raw
    .map((bar) => ({
      time: (bar.t ?? bar.time) as never,
      open: Number(bar.o ?? bar.open),
      high: Number(bar.h ?? bar.high),
      low: Number(bar.l ?? bar.low),
      close: Number(bar.c ?? bar.close),
    }))
    .filter(
      (bar) =>
        bar.time != null &&
        Number.isFinite(bar.open) &&
        Number.isFinite(bar.high) &&
        Number.isFinite(bar.low) &&
        Number.isFinite(bar.close),
    );
}

export function CandlestickArtifact({ artifact }: { artifact: ChatArtifact }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let disposed = false;
    let cleanup = () => {};

    // Imported inside the effect so the (large) charting library stays out of
    // any code path that never mounts a candlestick artifact.
    const palette = chartPalette();
    void import("lightweight-charts").then(({ createChart, CandlestickSeries }) => {
      if (disposed || !container) return;
      const chart = createChart(container, {
        height: 288,
        layout: { background: { color: "transparent" }, textColor: palette.axis },
        grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
        timeScale: { borderColor: palette.grid },
        rightPriceScale: { borderColor: palette.grid },
      });
      // Up is the buy token, down is the sell token — the same pair every other
      // direction signal uses, never a second green.
      const series = chart.addSeries(CandlestickSeries, {
        upColor: palette.buy,
        downColor: palette.sell,
        wickUpColor: palette.buy,
        wickDownColor: palette.sell,
        borderVisible: false,
      });
      series.setData(toBars(artifact.content));
      chart.timeScale().fitContent();
      cleanup = () => chart.remove();
    });

    return () => {
      disposed = true;
      cleanup();
    };
  }, [artifact.content]);

  return (
    <figure className="my-2 rounded border border-slate-700 bg-slate-900 p-3">
      {artifact.title ? (
        <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      <div ref={containerRef} className="w-full" dir="ltr" data-testid="candlestick-container" />
    </figure>
  );
}
