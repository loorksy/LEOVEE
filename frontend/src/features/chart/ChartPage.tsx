import { useEffect, useRef, useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { createChartEngine, type ChartEngine, type SemanticAnnotation } from "@/chart";
import { normalizeBackendCandle } from "@/chart/ChartDataAdapter";
import { getCandles } from "@/api/markets";
import { listChartAnnotations } from "@/api/chart";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { useChartStream } from "@/features/chart/useChartStream";
import {
  annotationListToMap,
  annotationMapToList,
  applyAnnotationEvent,
} from "@/features/chart/annotationStream";
import { BACKEND_TIMEFRAMES, backendTimeframeToChart } from "@/features/chart/timeframe";


const DEFAULT_TIMEFRAME = "H1";

export function ChartPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const symbol = (searchParams.get("symbol") ?? DEFAULT_SYMBOL).toUpperCase();
  const timeframe = searchParams.get("timeframe") ?? DEFAULT_TIMEFRAME;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const engineRef = useRef<ChartEngine | null>(null);
  const annotationsRef = useRef<Map<string, SemanticAnnotation>>(new Map());
  const [annotationCount, setAnnotationCount] = useState(0);

  const workspaceQuery = useWorkspaceId();

  const candlesQuery = useQuery({
    queryKey: ["candles", symbol, timeframe],
    queryFn: () => getCandles(symbol, timeframe),
  });

  const annotationsQuery = useQuery({
    queryKey: ["chart-annotations"],
    queryFn: () => listChartAnnotations(),
  });

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const engine = createChartEngine({ container: containerRef.current });
    engineRef.current = engine;
    return () => {
      engine.destroy();
      engineRef.current = null;
    };
  }, []);

  useEffect(() => {
    engineRef.current?.setSymbol(symbol);
    engineRef.current?.setTimeframe(backendTimeframeToChart(timeframe));
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!candlesQuery.data) return;
    engineRef.current?.applyCandles(candlesQuery.data.candles.map(normalizeBackendCandle));
  }, [candlesQuery.data]);

  useEffect(() => {
    if (!annotationsQuery.data) return;
    annotationsRef.current = annotationListToMap(annotationsQuery.data.items);
    engineRef.current?.applyAnnotations(annotationMapToList(annotationsRef.current));
    setAnnotationCount(annotationsRef.current.size);
  }, [annotationsQuery.data]);

  useChartStream({
    symbol,
    workspaceId: workspaceQuery.data,
    onCandle: (candle) => {
      engineRef.current?.applyCandlePatch(normalizeBackendCandle(candle));
    },
    onAnnotationEvent: (event) => {
      annotationsRef.current = applyAnnotationEvent(annotationsRef.current, event);
      engineRef.current?.applyAnnotations(annotationMapToList(annotationsRef.current));
      setAnnotationCount(annotationsRef.current.size);
    },
  });

  return (
    <div className="flex flex-1 flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-100">AI Analyst — Chart</h1>
        <div className="flex items-center gap-2 text-sm">
          <label htmlFor="chart-symbol" className="sr-only">
            Symbol
          </label>
          <input
            id="chart-symbol"
            value={symbol}
            onChange={(event) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set("symbol", event.target.value.toUpperCase());
                return next;
              })
            }
            className="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
          <label htmlFor="chart-timeframe" className="sr-only">
            Timeframe
          </label>
          <select
            id="chart-timeframe"
            value={timeframe}
            onChange={(event) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set("timeframe", event.target.value);
                return next;
              })
            }
            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          >
            {BACKEND_TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </div>
      </header>
      {candlesQuery.isError && (
        <p className="text-amber-400">Could not load candles for {symbol}.</p>
      )}
      <div
        ref={containerRef}
        data-testid="chart-container"
        className="min-h-[420px] flex-1 rounded-lg border border-slate-800 bg-leovee-panel"
      />
      <p className="text-xs text-slate-500" data-testid="annotation-count">
        {annotationCount} annotation(s) loaded · live updates via /ws/v1/stream
        (channels=annotations)
      </p>
    </div>
  );
}
